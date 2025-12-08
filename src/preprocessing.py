import os # Para el manejo del sistema operativo y rutas de archivos
import glob # Para la búsqueda de archivos mediante patrones (wildcards)
import numpy as np # Para el manejo de matrices numéricas y arrays para las imágenes
import rasterio # Para la lectura y escritura de datos geoespaciales raster (.tif)
from rasterio.warp import calculate_default_transform, reproject, Resampling # Herramientas para reproyección y alineación
from rasterio.features import rasterize # Para la conversión de vectores (polígonos) a raster
import geopandas as gpd # Para la lectura y manipulación de datos vectoriales (Shapefiles)
import pandas as pd # Para el manejo de tablas de datos y concatenación
from shapely.geometry import box # Para la creación de geometrías rectangulares (bounding box)
import re # Para buscar la fecha en el nombre del archivo

# --- CONFIGURACIÓN DE RUTAS ---
# Se define la ruta base del proyecto subiendo dos niveles desde la ubicación del script
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Directorio donde están los datos originales descargados
RAW_DIR = os.path.join(BASE_DIR, "data", "raw")
# Directorio donde se guardarán los rasters procesados y normalizados
PROCESSED_DIR = os.path.join(BASE_DIR, "data", "processed")
# Archivo maestro de referencia (SRTM) que define la grilla y proyección para todo el proyecto
REF_RASTER = os.path.join(RAW_DIR, "srtm_valdivia.tif") 

def get_reference_meta():
    """
    Obtiene metadata del raster maestro (Altura).

    Descripción:
        Lee el archivo 'srtm_valdivia.tif' para establecer el sistema de coordenadas (CRS), 
        transformación afín y dimensiones que se usarán como estándar para todas las demás capas.

    Salida:
        tuple: (meta (dict), data (numpy.array), bounds (BoundingBox)).
    """
    with rasterio.open(REF_RASTER) as src:
        return src.meta.copy(), src.read(1), src.bounds

def align_raster(source_path, output_name, fill_value=0):
    """
    Reproyecta y alinea un raster cualquiera al raster maestro.
    
    Entradas:
        source_path (str): Ruta del archivo raster de origen.
        output_name (str): Nombre del archivo de salida.
        fill_value (int/float, opcional): Valor para rellenar datos faltantes (NoData). Default 0.

    Descripción:
        Lee el raster de origen, calcula la transformación necesaria para coincidir con el 
        raster maestro (que es SRTM), realiza la reproyección usando remuestreo bilineal y guarda 
        el resultado normalizado.

    Salida:
        Archivo generado: Guarda el raster procesado en 'data/processed/{output_name}'.
    """
    # Verificación de seguridad: si el archivo origen no existe, se salta la función
    if not os.path.exists(source_path):
        print(f"Saltando {output_name}: No existe {os.path.basename(source_path)}")
        return
    
    # Obtiene los metadatos y límites del raster maestro (target)
    dst_meta, _, dst_bounds = get_reference_meta()
    # Define la ruta completa donde se guardará el archivo procesado
    output_path = os.path.join(PROCESSED_DIR, output_name)

    # Abre el raster de origen (source) que queremos alinear
    with rasterio.open(source_path) as src:
        # Calcula la nueva transformación afín y las nuevas dimensiones (ancho/alto)
        # para que el origen coincida con la proyección y límites del maestro
        transform, width, height = calculate_default_transform(
            src.crs, dst_meta['crs'], dst_meta['width'], dst_meta['height'], *dst_bounds
        )
        # Se actualiza el diccionario de metadatos con los nuevos valores calculados
        dst_meta.update({
            'crs': dst_meta['crs'],       # Sistema de coordenadas del maestro
            'transform': transform,       # Nueva transformación espacial
            'width': width,               # Nuevo ancho en píxeles
            'height': height,             # Nuevo alto en píxeles
            'nodata': fill_value,         # Valor para píxeles vacíos
            'dtype': 'float32'            # Estandarizamos a float32 para cálculos numéricos
        })
        # Se crea un array vacío de numpy con las nuevas dimensiones para recibir los datos
        destination = np.zeros((height, width), dtype='float32')
        # Se ejecuta la reproyección: transforma los píxeles del origen al destino
        reproject(
            source=rasterio.band(src, 1),   # Fuente: Banda 1 del archivo original
            destination=destination,        # Destino: El array vacío creado arriba
            src_transform=src.transform,    # Transformación original
            src_crs=src.crs,                # CRS original
            dst_transform=transform,        # Transformación destino
            dst_crs=dst_meta['crs'],        # CRS destino
            resampling=Resampling.bilinear  # Método de interpolación (bilineal suaviza los valores)
        )
        # Guarda el resultado en el disco con los nuevos metadatos
        with rasterio.open(output_path, 'w', **dst_meta) as dst:
            dst.write(destination, 1)
    # Mensaje de éxito, en caso de raster procesado correctamente
    print(f"Raster procesado: {output_name}")

def extract_date_from_filename(filename):
    """
    Intenta extraer una fecha (YYYYMMDD) del nombre del archivo.

    Entradas:
        filename (str): Nombre del archivo (ejemplo: 'FireScar_20150215.shp').
    
    Descripción:
        Utiliza una expresión regular para buscar una secuencia de 8 dígitos (YYYYMMDD) 
        dentro de la cadena de texto proporcionada.

    Salida:
        int: La fecha como entero (ej. 20150215) o 0 si no encuentra coincidencia.
    """
    # Busca un patrón de exactamente 8 dígitos consecutivos en el nombre
    match = re.search(r'(\d{8})', filename)
    if match: # Si encuentra, retorna el número entero (ej: 20150215)
        return int(match.group(1))
    return 0 # Si no encuentra fecha, retorna 0

def process_fires(cumulative_output="grid_incendios_historicos.tif", recent_output="grid_incendio_reciente.tif"):
    """
    Procesa los shapefiles de incendios para generar capas raster.

    Entradas:
        cumulative_output (str): Nombre del archivo de salida para el acumulado histórico
        recent_output (str): Nombre del archivo de salida para el incendio más reciente en Valdivia
    
    Descripción:
        1. Busca shapefiles en la carpeta de Pangaea.
        2. Filtra aquellos que intersectan geométricamente con el área de Valdivia.
        3. Genera un raster acumulado sumando todas las geometrías válidas ("Grid Histórico").
        4. Identifica el incendio con la fecha más reciente y lo rasteriza por separado ("Grid Reciente" para simulación).

    Salidas:
        Dos archivos .tif en la carpeta 'data/processed/':
            1. Acumulado histórico (suma de todos): grid_incendios_historicos.tif.
            2. El más reciente encontrado (para simulación): grid_incendio_reciente.tif.
    """
    # Define la ruta donde están los shapefiles descomprimidos
    pangaea_dir = os.path.join(RAW_DIR, "incendios_pangaea")
    print(f"\nBuscando incendios en: {pangaea_dir} ...")
    # Lista para almacenar rutas de todos los shapefiles encontrados
    all_shps = []
    # Recorre recursivamente (os.walk) la carpeta buscando archivos .shp que empiecen con "FireScar"
    for root, dirs, files in os.walk(pangaea_dir):
        for file in files:
            if file.startswith("FireScar") and file.endswith(".shp"):
                all_shps.append(os.path.join(root, file))
    # Si no encuentra nada, avisa y termina la función
    if not all_shps:
        print("No se encontraron archivos shapefile.")
        return
    # Se obtiene la geometría y proyección del área de estudio (ciudad de Valdivia)
    dst_meta, _, dst_bounds = get_reference_meta()
    # Se crea un objeto 'box' (rectángulo) con las coordenadas del raster maestro
    bbox_valdivia = box(*dst_bounds)
    
    # Lista para guardar tuplas con datos procesados: (fecha, geodataframe, nombre_archivo)
    valid_fires = []

    print(f"   Analizando {len(all_shps)} archivos...")
    # Recorre cada shapefile encontrado
    for shp_path in all_shps:
        try:
            gdf = gpd.read_file(shp_path) # Carga el shapefile con Geopandas
            # Reproyecta el shapefile si su sistema de coordenadas es distinto al maestro
            # Esto es crucial para poder comparar geométricamente
            if gdf.crs != dst_meta['crs']:
                gdf = gdf.to_crs(dst_meta['crs'])

            # Verificar intersección
            # Ve si alguna parte del incendio cae dentro de la bounding box de Valdivia
            if gdf.intersects(bbox_valdivia).any():
                # Recorta (clip) el shapefile para quedarse solo con la parte dentro de Valdivia
                gdf_clipped = gdf[gdf.intersects(bbox_valdivia)]
                # Si después del recorte queda algo de geometría válida
                if not gdf_clipped.empty:
                    # Extrae la fecha del nombre del archivo para poder ordenar cronológicamente
                    date_num = extract_date_from_filename(os.path.basename(shp_path))
                    # Guarda los datos en la lista valid_fires
                    valid_fires.append((date_num, gdf_clipped, os.path.basename(shp_path)))
                    print(f"    MATCH ({date_num}): {os.path.basename(shp_path)}")
        # Si hay un error leyendo un archivo específico, lo salta sin romper el programa
        except Exception as e: 
            pass
    # Si después de filtrar no quedó ningún incendio válido en la zona
    if not valid_fires:
        print("  Ningún incendio cae en Valdivia. Generando rasters vacíos.")
        # Se crea una matriz de ceros (imagen negra)
        empty_arr = np.zeros((dst_meta['height'], dst_meta['width']), dtype=rasterio.uint8)
        # Actualiza metadatos para formato entero (uint8)
        dst_meta.update({'dtype': 'uint8', 'nodata': 0, 'count': 1})
        # Guarda los rasters vacíos en disco para que el pipeline no falle después
        with rasterio.open(os.path.join(PROCESSED_DIR, cumulative_output), 'w', **dst_meta) as dst:
            dst.write(empty_arr, 1)
        with rasterio.open(os.path.join(PROCESSED_DIR, recent_output), 'w', **dst_meta) as dst:
            dst.write(empty_arr, 1)
        return

    # --- 1. GENERAR ACUMULADO (HISTÓRICO) ---
    print(f"\n    Generando mapa acumulado de {len(valid_fires)} incendios...")
    # Concatena todos los GeoDataFrames válidos en uno solo gigante
    all_gdfs = pd.concat([f[1] for f in valid_fires], ignore_index=True)
    # Prepara un generador de tuplas (geometria, valor_quemado=1) para la función rasterize
    shapes_all = ((geom, 1) for geom in all_gdfs.geometry)
    # Convierte los vectores (polígonos) a una imagen raster (grilla de píxeles)
    # Donde hay incendio pone 1, donde no, pone 0
    raster_all = rasterize(
        shapes=shapes_all, 
        out_shape=(dst_meta['height'], dst_meta['width']), # Mismas dimensiones que el SRTM
        transform=dst_meta['transform'],
        fill=0, # Fondo negro (0)
        dtype=rasterio.uint8
    )
    # Prepara metadatos y guarda el archivo histórico
    dst_meta.update({'dtype': 'uint8', 'nodata': 0, 'count': 1})
    with rasterio.open(os.path.join(PROCESSED_DIR, cumulative_output), 'w', **dst_meta) as dst:
        dst.write(raster_all, 1)
    print(f" Guardado: {cumulative_output}")

    # --- 2. GENERAR RECIENTE (SIMULACIÓN) ---
    # Ordenamos la lista valid_fires por fecha (índice 0 de la tupla) de mayor a menor (reverse=True)
    valid_fires.sort(key=lambda x: x[0], reverse=True)
    # Tomamos el primer elemento (el más reciente)
    latest_date, latest_gdf, latest_name = valid_fires[0]
    print(f"\n   Incendio más reciente: {latest_name} (Fecha: {latest_date})")
    # Preparamos las geometrías solo de este incendio específico
    shapes_recent = ((geom, 1) for geom in latest_gdf.geometry)
    # Rasterizamos solo este incendio
    raster_recent = rasterize(
        shapes=shapes_recent,
        out_shape=(dst_meta['height'], dst_meta['width']),
        transform=dst_meta['transform'],
        fill=0,
        dtype=rasterio.uint8
    )
    # Guardamos el archivo "reciente"
    with rasterio.open(os.path.join(PROCESSED_DIR, recent_output), 'w', **dst_meta) as dst:
        dst.write(raster_recent, 1)
    print(f" Guardado: {recent_output}")

def main():
    """
    Orquestador principal del preprocesamiento.

    Descripción:
        Ejecuta el pipeline completo de procesamiento:
        1. Crea el directorio de procesados.
        2. Alinea las capas base (SRTM, Sentinel, ERA5).
        3. Alinea las capas de CONAF (Amenaza, Riesgo).
        4. Procesa y rasteriza los vectores de incendios históricos (y el más reciente).

    Salida:
        Archivos generados: Múltiples rasters normalizados en 'data/processed/' y mensajes de estado en consola.
    """
    # Si no existe la carpeta de salida (processed), la crea
    if not os.path.exists(PROCESSED_DIR):
        os.makedirs(PROCESSED_DIR)

    print(" --- INICIANDO PREPROCESAMIENTO ---")

    # 1. Capas Base: Alineamos topografía, vegetación y clima al mismo formato
    align_raster(REF_RASTER, "grid_altura.tif")
    align_raster(os.path.join(RAW_DIR, "sentinel2_valdivia.tif"), "grid_vegetacion.tif")
    align_raster(os.path.join(RAW_DIR, "era5_wind_valdivia.tif"), "grid_viento.tif")
    
    # 2. Capas CONAF: Alineamos mapas oficiales de amenaza y riesgo
    # Nota importante: Se asumen nombres de archivo específicos ("14_amenaza.tif", etc.)
    align_raster(os.path.join(RAW_DIR, "conaf_amenaza", "raster", "14_amenaza.tif"), "grid_amenaza.tif")
    align_raster(os.path.join(RAW_DIR, "conaf_riesgo", "raster", "14_riesgo.tif"), "grid_riesgo.tif")

    # 3. INCENDIOS: Ejecutamos la lógica compleja de vectores a raster
    process_fires(cumulative_output="grid_incendios_historicos.tif", 
                  recent_output="grid_incendio_reciente.tif")

    print("\n Preprocesamiento finalizado.") # Mensaje de éxito para el fin del preprocesamiento

# Bloque estándar para ejecutar el script solo si se llama directamente
if __name__ == "__main__":
    main()