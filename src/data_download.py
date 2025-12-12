import os                   # Para el manejo de rutas y archivos
import argparse             # Para crear interfaz de línea de comandos (CLI)
import requests             # Para descargar archivos desde URLs
import zipfile              # Para manejar archivos ZIP
import io                   # Para manejar streams de bytes (útil para ZIP en memoria)
import sys                  # Funciones utilitarias del sistema
import ee                   # Google Earth Engine API
import geemap               # Librería que facilita exportar imágenes desde GEE (Google Earth Engine)
import gdown                # Para descargar carpetas/archivos desde Google Drive

# --- CONFIGURACIÓN GLOBAL ---
# Coordenadas de Valdivia, Región de Los Ríos (Bounding Box aproximado)
# [Oeste, Sur, Este, Norte]
VALDIVIA_BBOX = [-73.30, -39.88, -73.16, -39.75]
DATA_RAW_PATH = os.path.join("data", "raw") # ruta donde se guardarán los datos descargados
# CONSTANTE GLOBAL: El ID de proyecto compartido. Para acceder a Google Earth Engine
DEFAULT_GEE_PROJECT = "composed-augury-451119-b6" # Esto permite correr el script sin configurar nada extra

# ID de la carpeta pública que creé de Google Drive con la topologia, vegetación y viento de Valdivia
BACKUP_DRIVE_FOLDER_ID = "1eAiuHibNpdkmZO3n806hPpca-lf7623K" # sirve de respaldo, si falla la autenticación en GEE

# Variable global para controlar si GEE está disponible o usamos respaldo
GEE_AVAILABLE = False

def init_gee():
    """
    Función para inicializar Google Earth Engine (GEE) 

    Descripción: Configura la sesión de GEE intentando 3 métodos de autenticación en orden de prioridad:
        1. Variable de entorno (si el usuario configuró la suya)
        2. ID del proyecto por defecto del equipo (compartido con el profesor y equipo)
        3. Autenticación interactiva (vía navegador) si falla lo anterior
        
    Nota: Si todo falla, activa el modo RESPALDO para descargar desde Drive público creado por el grupo.

    Salida: 
        No retorna valor (None), pero inicializa la sesión global de la librería ee (Google Earth Engine)
        y actualiza la variable global GEE_AVAILABLE.
    """
    global GEE_AVAILABLE
    
    # 1. Intentar con variable de entorno
    project = os.environ.get('GOOGLE_CLOUD_PROJECT') or os.environ.get('EE_PROJECT')
    
    # 2. Si no hay variables definidas, se usa el ID del proyecto compartido
    if not project:
        project = DEFAULT_GEE_PROJECT
    
    print(f"Intentando conectar a GEE con proyecto: {project}...")

    # Se intenta inicializar con el proyecto compartido
    try:
        # Intentamos inicializar directo
        ee.Initialize(project=project)
        print(f"GEE inicializado correctamente (project={project}).")
        GEE_AVAILABLE = True
        return
    
    # 3. Si falla, intentamos autenticar al usuario
    except Exception:
        print(f"ADVERTENCIA: Credenciales no encontradas o expiradas para el proyecto {project}.")
        print("ADVERTENCIA: Iniciando autenticación interactiva (sigue las instrucciones en el navegador)...")
        # Intento autenticar
        try:
            # Fuerza la autenticación
            ee.Authenticate() # # Autenticación interactiva a través del navegador
            # Reintenta inicializar con tu proyecto después de autenticar
            ee.Initialize(project=project)
            print(f"EXITO: GEE inicializado y autenticado exitosamente (project={project}).")
            GEE_AVAILABLE = True
            return
        # Si falla la autenticación, activamos el Plan B (Un Google Drive de respaldo)
        except Exception as e_final:
            print(f"ERROR: Error fatal iniciando GEE: {e_final}")
            print("AVISO: Se activará el modo RESPALDO (Descarga estática desde Drive).")
            print("   No se requiere cuenta de Google Earth Engine para continuar.")
            GEE_AVAILABLE = False

        
def get_roi():
    """
    Función para retornar la geometría de la zona de estudio (Valdivia)

    Descripción: 
        Genera un objeto geométrico de Earth Engine basado en las coordenadas 
        definidas en VALDIVIA_BBOX. Usandose como región de recorte (clip) para
        recortar las imágenes satelitales en las descargas desde GEE.

    Salidas: 
        ee.Geometry.Rectangle: Objeto geométrico que representa el bounding box de Valdivia
    """
    return ee.Geometry.Rectangle(VALDIVIA_BBOX) # Crea un rectángulo con las coordenadas de Valdivia [Oeste, Sur, Este, Norte]

# --- Función de respaldo para topología, vegetación y viento ---

def download_from_backup(filename):
    """
    Descripción: 
        Descarga un archivo específico desde la carpeta de respaldo en Drive público creado por el grupo.
        Se usa cuando GEE falla o no está configurado.

    Entradas:
        filename (str): Nombre del archivo a descargar desde la carpeta de respaldo.
    
    Salida: 
        Descarga el archivo especificado en data/raw/filename
    """
    print(f"\n Modo Respaldo: Descargando {filename} desde Drive...")
    
    # La URL de descarga de carpeta de gdown usando el ID del backup
    url = f'https://drive.google.com/drive/folders/{BACKUP_DRIVE_FOLDER_ID}'
    
    try:
        # gdown descarga la carpeta, pero verifica si los archivos existen para no bajar doble
        # Descargamos en data/raw
        gdown.download_folder(url, output=DATA_RAW_PATH, quiet=False, use_cookies=False)
        # Verificación simple
        expected_path = os.path.join(DATA_RAW_PATH, filename)
        if os.path.exists(expected_path):
            print(f"{filename} recuperado exitosamente del respaldo.")
        else: # En caso de que no se encuentre el archivo dentro del drive
            print(f"Se descargó el respaldo, pero no se encuentra {filename}.")
            
    except Exception as e: # En caso de error en la descarga
        print(f"Error descargando respaldo de Drive: {e}")

# --- FUNCIONES DE DESCARGA ---
# - Altura (Topografía): SRTM (Valdivia)
# - Densidad vegetal (combustible): sentinel2 (Valdivia)
# - Capa de viento: era5 (Valdivia)
# - Incendios históricos: pangaea (Región de los Ríos)
# - Riesgo y amenaza de incendios: CONAF (Región de los Ríos)

def download_srtm():
    """
    Descarga datos de topología (SRTM) - Altura

    Descripción:
        Descarga el modelo digital de elevación SRTM (resolución 30 m)
        Obtiene datos de topografía (elevación) del dataset SRTM (resolución 30m) 
        desde Google Earth Engine, recortando la imagen a la zona de Valdivia y la exporta localmente.
        
        Plan B: Si GEE no está disponible, descarga el archivo pre-procesado desde Drive.
    
    Datos:
        - Origen: USGS/SRTMGL1_003
        - Formato de salida: .tif
        - Ciudad: Bounding box de Valdivia
        - Resolución exportada: 30m (nativa)
     
    Salida: 
        Archivo generado: data/raw/srtm_valdivia.tif 
    """
    target_file = "srtm_valdivia.tif"
    
    # Si GEE está disponible, usamos el método original
    if GEE_AVAILABLE:
        print("\nIniciando descarga: SRTM (Topología)...")
        try:
            # Obtengo el bounding box de Valdivia que se usará para recortar la imagen
            roi = get_roi()
            # Carga imagen SRTM 30m desde GEE y la recorta a Valdivia
            image = ee.Image("USGS/SRTMGL1_003").clip(roi) # Dataset SRTM 30m
            # Ruta donde se guardará el archivo TIFF exportado: data/raw/srtm_valdivia.tif
            filename = os.path.join(DATA_RAW_PATH, target_file)
            # Exporta la imagen al disco local usando geemap
            geemap.ee_export_image(image, filename=filename, scale=30, region=roi)
            print(f"EXITO: SRTM descargado en: {filename}")
        except Exception as e: # En caso de error, intentamos el respaldo
            print(f"ERROR en GEE: {e}. Intentando descarga de respaldo...")
            download_from_backup(target_file)
    else:
        # Si GEE no está disponible, vamos directo al respaldo
        download_from_backup(target_file)

def download_sentinel2():
    """
    Descarga datos de vegetación (Sentinel-2) de verano con baja nubosidad.
    
    Descripción:
        Busca imágenes de la colección Sentinel-2 para el verano de 2024, filtrando por baja 
        nubosidad (<10%), seleccionando la imagen más limpia, recortando a la zona de interés 
        y exportando las bandas B4, B8, B3 y B2.
        
        Plan B: Si GEE no está disponible, descarga el archivo pre-procesado desde Drive.

    Salida: 
        Archivo generado: data/raw/sentinel2_valdivia.tif
    """
    target_file = "sentinel2_valdivia.tif"

    if GEE_AVAILABLE:
        print("\nIniciando descarga: Sentinel-2 (Vegetación)...")
        try:
            roi = get_roi() # Obtengo la bounding box de recorte (de Valdivia)
            # Filtramos por fecha de verano (temporada incendios) y pocas nubes
            # Nota: Usamos la colección HARMONIZED si es posible para evitar warnings, o la estándar
            image = (ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
                     .filterBounds(roi)
                     .filterDate('2024-01-01', '2024-03-01')
                     .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 10))
                     .sort('CLOUDY_PIXEL_PERCENTAGE') # Ordena por menos nubes
                     .first()                         # Toma la imagen más limpia
                     .clip(roi))
            # Si no hay imágenes sin nubes, se informa y se usa respaldo
            if image is None:
                print("ADVERTENCIA: No se encontraron imágenes Sentinel-2 sin nubes. Usando respaldo...")
                download_from_backup(target_file)
                return
            # Se genera ruta de salida para la descarga: data/raw/sentinel2_valdivia.tif        
            filename = os.path.join(DATA_RAW_PATH, target_file)
            # Descargamos bandas clave para NDVI (B4=Red, B8=NIR) y Visual (B2=Azul, B3=Verde)       
            # Scale 10m es la resolución nativa de Sentinel
            geemap.ee_export_image(image.select(['B4', 'B8', 'B3', 'B2']), 
                                   filename=filename, scale=10, region=roi)
            print(f"EXITO: Sentinel-2 descargado en: {filename}")
        except Exception as e: # En caso de error, intentamos el respaldo
            print(f"ERROR en GEE: {e}. Intentando descarga de respaldo...")
            download_from_backup(target_file)
    else:
        download_from_backup(target_file)

def download_era5():
    """
    Descarga promedio mensual de viento ERA5-Land.
    
    Descripción:
        Obtiene datos horarios de ERA5-Land, calculando el promedio mensual de las componentes 
        del viento (U y V) para el verano de 2024 a 10m de altura, y exporta el resultado 
        con un reescalado a 1000 metros (1km).
        
        Plan B: Si GEE no está disponible, descarga el archivo pre-procesado desde Drive.

    Salida:
        Archivo generado: 'data/raw/era5_wind_valdivia.tif'.
    """
    target_file = "era5_wind_valdivia.tif"

    if GEE_AVAILABLE:
        print("\nIniciando descarga: ERA5 (Viento)...")
        try:
            roi = get_roi() # Obtengo la bounding box de recorte (de Valdivia)
            # ERA5 Land Hourly - Filtramos un promedio del verano para el modelo base
            # Seleccionamos componentes U y V del viento a 10m de altura
            # Carga colección ERA5 por fecha + zona
            collection = (ee.ImageCollection("ECMWF/ERA5_LAND/HOURLY")
                          .filterBounds(roi)
                          .filterDate('2024-01-01', '2024-02-01')
                          .select(['u_component_of_wind_10m', 'v_component_of_wind_10m']))
            
            # Reducimos a un promedio temporal para tener una "imagen" base del viento predominante
            image = collection.mean().clip(roi) # Calcula promedio mensual para suavizar
            # Se genera la ruta de salida para la descarga: data/raw/era5_wind_valdivia.tif
            filename = os.path.join(DATA_RAW_PATH, target_file)
            # ERA5 tiene baja resolución (11km), pero exportamos a 100m para suavizar
            # Exporta con resolución "suavizada" (1000m)
            geemap.ee_export_image(image, filename=filename, scale=1000, region=roi)
            print(f"EXITO: ERA5 (Viento) descargado en: {filename}")
        except Exception as e: # En caso de error, intentamos el respaldo
            print(f"ERROR en GEE: {e}. Intentando descarga de respaldo...")
            download_from_backup(target_file)
    else:
        download_from_backup(target_file)

def download_pangaea():
    """
    Descarga datos históricos de incendios (Pangaea ZIP).

    Descripción:
        Realiza una petición HTTP GET para descargar un archivo ZIP desde el repositorio 
        de la página de Pangaea, el cual contiene shapefiles de cicatrices de incendios (FireScar) 
        para la Región de Los Ríos. Y se descomprime el contenido automáticamente.

        Nota: Esta función descarga el ZIP pero solo extrae los archivos vectoriales (.shp y auxiliares),
        ahorrando tiempo de escritura en disco y espacio de almacenamiento.
    
    Salida: 
        Carpeta generada: data/raw/incendios_pangaea/ y su contenido descomprimido.
    """
    print("\nIniciando descarga: Incendios Históricos (Pangaea)...")
    # URL directa del ZIP del dataset de Los Ríos (región actual de Valdivia)
    # en esta URL está el registro histórico de incendios para Los Ríos, por parte de la CONAF
    direct_zip_url = "https://download.pangaea.de/dataset/941127/files/FireScar_CL-LR_LosRios_1985-2018.zip"
    extract_path = os.path.join(DATA_RAW_PATH, "incendios_pangaea")

    # Extensiones necesarias para que funcione un Shapefile en GeoPandas
    extensiones_utiles = ('.shp', '.shx', '.dbf', '.prj', '.cpg', '.fix')
    try: # Solicita el ZIP desde internet
        # Conexión en modo stream (flujo de datos)
        response = requests.get(direct_zip_url, stream=True)
        total_size = int(response.headers.get('content-length', 0))
        if response.status_code == 200: # Si la descarga fue exitosa (200), se procesa el ZIP
            # Buffer en memoria para guardar el ZIP
            buffer = io.BytesIO()
            downloaded = 0
            chunk_size = 1024 * 1024 # 1MB por trozo
            print(f"   Tamaño del archivo: {total_size / (1024*1024):.2f} MB")
            # Bucle de descarga con barra de progreso
            for data in response.iter_content(chunk_size=chunk_size):
                buffer.write(data)
                downloaded += len(data)
                # Cálculo de porcentaje
                if total_size > 0:
                    percent = int(50 * downloaded / total_size)
                    # Barra visual: [=====     ] 50%
                    sys.stdout.write(f"\r   Descargando: [{'=' * percent}{' ' * (50 - percent)}] {downloaded / total_size:.0%}")
                    sys.stdout.flush()
            print("\n   Descarga completada. Iniciando extracción selectiva...")
            # Extracción selectiva con contador
            z = zipfile.ZipFile(buffer) # Carga ZIP en memoria
            file_list = z.infolist()
            total_files = len(file_list)
            # Filtramos archivo por archivo dentro del ZIP
            archivos_extraidos = 0
            for i, file_info in enumerate(file_list):
                # Feedback visual en la misma línea
                sys.stdout.write(f"\r   Analizando archivo {i+1}/{total_files}...")
                sys.stdout.flush()
                # Solo extraemos si es un archivo vectorial (FireScar) y tiene extensión útil
                if "FireScar" in file_info.filename and file_info.filename.lower().endswith(extensiones_utiles):
                    z.extract(file_info, extract_path)
                    archivos_extraidos += 1
            print(f"\nEXITO: Se extrajeron {archivos_extraidos} archivos vectoriales en: {extract_path}")
        else: # Si la descarga falla, se informa al usuario para descarga manual
            print(f"ADVERTENCIA: No se pudo descargar automáticamente (Status {response.status_code}).")
            print(f"Por favor descarga manual: {direct_zip_url}")

    except Exception as e:
        print(f"\nERROR: Error en descarga Pangaea: {e}")


def download_comuna_valdivia():
    """
    Descarga y procesa el shapefile oficial de comunas (Geoportal.cl),
    extrayendo solamente la comuna de Valdivia.

    Flujo:
        1. Descarga ZIP desde Geoportal.
        2. Extrae el archivo 'DPA_2023'.
        3. Elimina el ZIP.
        4. Entra a 'COMUNAS/' dentro del paquete.
        5. Filtra la comuna de Valdivia.
        6. Guarda el shapefile resultante en data/raw/comuna/comuna_valdivia.*

    Archivos generados:
        data/raw/comuna/comuna_valdivia.shp (+ .dbf, .shx, .prj)
    """

    import requests
    import zipfile
    import shutil
    import geopandas as gpd

    print("\nIniciando descarga: Comunas (Geoportal.cl)...")

    # --- 1. Configuración de rutas ---
    zip_url = "https://www.geoportal.cl/geoportal/catalog/download/912598ad-ac92-35f6-8045-098f214bd9c2"
    zip_path = os.path.join(DATA_RAW_PATH, "DPA_2023.zip")
    comunas_path = os.path.join(DATA_RAW_PATH, "COMUNAS")
    output_dir = os.path.join(DATA_RAW_PATH, "comuna")

    # Crear carpeta comuna si no existe
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # --- 2. Descargar ZIP ---
    try:
        print(" Descargando ZIP desde Geoportal.cl ...")
        response = requests.get(zip_url, stream=True)

        if response.status_code != 200:
            print(f"ERROR: No se pudo descargar el archivo (status: {response.status_code})")
            return

        with open(zip_path, "wb") as f:
            f.write(response.content)

        print(" ZIP descargado correctamente.")

    except Exception as e:
        print(f"ERROR durante la descarga del ZIP: {e}")
        return

    # --- 3. Extraer contenido ---
    try:
        print(" Extrayendo DPA_2023.zip ...")

        with zipfile.ZipFile(zip_path, "r") as z:
            z.extractall(DATA_RAW_PATH)

        print(" ZIP extraído correctamente.")

        # Eliminar ZIP
        os.remove(zip_path)
        print(" ZIP eliminado por limpieza.")

    except Exception as e:
        print(f"ERROR al extraer el ZIP: {e}")
        return

    # --- 4. Obtener shapefile de comunas ---
    
    shp_file = os.path.join(comunas_path, "COMUNAS_v1.shp")

    if not os.path.exists(shp_file):
        print("ERROR: No se encontró COMUNAS_v1.shp dentro de DPA_2023/comunas/")
        return

    print(" Leyendo COMUNAS_v1.shp ...")
    try:
        gdf = gpd.read_file(shp_file)
    except Exception as e:
        print(f"ERROR al leer el shapefile: {e}")
        return

    # --- 5. Filtrar comuna Valdivia ---
    print(" Filtrando comuna de Valdivia ...")
    # Los datasets oficiales usan nombres en mayúsculas
    gdf_valdivia = gdf[gdf["COMUNA"].str.upper() == "VALDIVIA"]

    if gdf_valdivia.empty:
        print("ERROR: No se encontró la comuna de Valdivia en el shapefile.")
        return

    # --- 6. Guardar shapefile resultante ---
    output_shp = os.path.join(output_dir, "comuna_valdivia.shp")

    try:
        gdf_valdivia.to_file(output_shp)
        print(f"EXITO: Shapefile de Valdivia guardado en: {output_shp}")
    except Exception as e:
        print(f"ERROR al guardar shapefile final: {e}")
        return

    print("Proceso de comuna Valdivia finalizado.")


def download_conaf():
    """
    Descarga datos oficiales de amenaza y riesgo de CONAF.

    Nota: Descarga solo las subcarpetas de la Región 14 (Los Ríos) 
    desde CONAF. Para evitar descargar terabytes de datos de otras regiones

    Descripción:
        Utiliza la librería gdown para descargar carpetas específicas desde Google Drive 
        que contienen rasters y shapefiles de la Región de Los Ríos (Región 14), evitando 
        descargar el dataset nacional completo
        Cabe destacar que este enlace Drive se obtuvo desde la página oficial de CONAF.

    Salida: 
        Carpetas generadas: data/raw/conaf_amenaza/ y data/raw/conaf_riesgo/ con su contenido.
    """
    print("\nIniciando descarga: CONAF (Solo Región 14 - Los Ríos)...")
    
    try:
        import gdown # Verifica que gdown esté instalado
    except ImportError: # En caso que no esté instalado gdown
        print("ERROR: Falta librería gdown. Ejecuta: pip install gdown")
        return

    # Enlaces de las carpetas de Google Drive que deben descargarse:
    # correspondiente a conaf_amenaza (raster y shapefiles) y conaf_riesgo (raster y shapefiles)
    carpetas_target = {
        "Amenaza_Raster": {
            "id": "1xc8qTlR6WsFtO4bt5gth_H3p0ENtJCK1", # (Amenaza Raster)
            "path": os.path.join(DATA_RAW_PATH, "conaf_amenaza", "raster")
        },
        "Amenaza_Shapefile": {
            "id": "1EkwZdg0lUUruyEDPau_Gpa6W--4PI2NQ", # (Amenaza Shapefile)
            "path": os.path.join(DATA_RAW_PATH, "conaf_amenaza", "shapefiles")
        },
        "Riesgo_Raster": {
            "id": "1j3nKVJuwi04gjlbiSmEbRWmyJkZRIM9Z", # (Riesgo Raster)
            "path": os.path.join(DATA_RAW_PATH, "conaf_riesgo", "raster")
        },
        "Riesgo_Shapefile": {
            "id": "1zywr5_DbGmtm0sYZSS3i75yivuP1QGPK", # (Riesgo Shapefile)
            "path": os.path.join(DATA_RAW_PATH, "conaf_riesgo", "shapefiles")
        }
    }
    # Recorre cada carpeta a descargar
    for nombre, info in carpetas_target.items():
        print(f"--- Descargando {nombre} (Valdivia)... ---")
        # Crear carpeta destino si no existe
        if not os.path.exists(info["path"]):
            os.makedirs(info["path"])
        try:
            # url format para gdown
            # Construye URL de carpeta de Google Drive
            url = f'https://drive.google.com/drive/folders/{info["id"]}'
            # Descarga las carpetas usando gdown
            # quiet=False para ver el progreso
            gdown.download_folder(url, output=info["path"], quiet=False, use_cookies=False)
            print(f"    EXITO: {nombre} completado.")
        except Exception as e:
            print(f"    ERROR: Error en {nombre}: {e}")

# --- GESTOR PRINCIPAL ---
# Función principal (main): gestiona la descarga de datos según argumentos CLI

# Comandos a ejecutar para descargar los datos
# Para topología: python src/data_download.py --sources srtm
# Para vegetación: python src/data_download.py --sources sentinel2
# Para viento: python src/data_download.py --sources era5
# Para incendios: python src/data_download.py --sources pangaea
# Para amenaza y riesgo de incendios: python src/data_download.py --sources conaf
# Para descargar todos los datos a la vez: python src/data_download.py --sources all

def main():
    """
    Orquestador principal del script de descarga (CLI).

    Entradas:
        Argumentos de línea de comandos (--sources) procesados mediante argparse.
        Opciones disponibles: 'srtm', 'sentinel2', 'era5', 'pangaea', 'conaf', 'all'.
    
    Descripción:
        Gestiona el flujo de descarga: crea directorios necesarios, inicializa GEE 
        (solo si las fuentes solicitadas lo requieren) y ejecuta las funciones de 
        descarga correspondientes según lo solicitado por el usuario.

    Salida:
        Mensajes de estado en consola y ejecución de funciones de descarga (según lo solicitado).
    """
    # Asegurar que existe la carpeta
    if not os.path.exists(DATA_RAW_PATH): # Crea carpeta data/raw si no existe
        os.makedirs(DATA_RAW_PATH)
        print(f"📂 Carpeta creada: {DATA_RAW_PATH}")
    # Parser de argumentos para CLI
    parser = argparse.ArgumentParser(description="Script de descarga de datos geoespaciales para Firescope.")
    # Diccionario para asignar nombre a las funciones
    available_sources = {
        'srtm': download_srtm, # topología
        'sentinel2': download_sentinel2, # vegetación
        'era5': download_era5, # viento
        'pangaea': download_pangaea, # incendios
        'conaf': download_conaf, # amenaza y riesgo de incendios
        'comuna': download_comuna_valdivia

    }
    # Argumento obligatorio --sources: para indicar desde que fuente se quiere descargar los datos
    parser.add_argument('--sources', nargs='+', required=True,
                        choices=list(available_sources.keys()) + ['all'],
                        help='Lista de fuentes a descargar (separadas por espacio) o "all".')
    args = parser.parse_args() # Parsea los argumentos ingresados por el usuario
    sources_to_run = []

    # Determina qué fuentes se deben correr
    if 'all' in args.sources: # si se coloca all, se descargan todas las fuentes
        sources_to_run = list(available_sources.keys())
    else:
        sources_to_run = args.sources # si no, se descarga desde las fuentes indicadas en el comando

    # Inicializar GEE solo si es necesario (para srtm, sentinel, era5)
    # Se intentará inicializar GEE, si falla, se activará GEE_AVAILABLE = False
    gee_needed = any(s in ['srtm', 'sentinel2', 'era5'] for s in sources_to_run)
    if gee_needed:
        init_gee()

    # Ejecutar descargas
    print("="*40)
    print(f"Iniciando pipeline para: {', '.join(sources_to_run)}")
    print(f"Modo GEE disponible: {GEE_AVAILABLE}")
    print("="*40)
    # Ejecuta cada descarga solicitada
    for source in sources_to_run:
        available_sources[source]()
    print("\nProceso finalizado.") # Mensaje de proceso finalizado

# Ejecuta main() solo si el script se corre directamente
if __name__ == "__main__":
    main()