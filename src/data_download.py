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

def init_gee():
    """
    Función para inicializar Google Earth Engine (GEE) 

    Descripción: Configura la sesión de GEE intentando 3 métodos de autenticación en orden de prioridad:
        1. Variable de entorno (si el usuario configuró la suya)
        2. ID del proyecto por defecto del equipo (compartido con el profesor y equipo)
        3. Autenticación interactiva (vía navegador) si falla lo anterior

    Salida: 
        No retorna valor (None), pero inicializa la sesión global de la librería ee (Google Earth Engine)
    """
    # 1. Intentar con variable de entorno
    project = os.environ.get('GOOGLE_CLOUD_PROJECT') or os.environ.get('EE_PROJECT')
    
    # 2. Si no hay variables definidas, se usa el ID del proyecto compartido
    if not project:
        project = DEFAULT_GEE_PROJECT
    # Se intenta inicializar con el proyecto compartido
    try:
        # Intentamos inicializar directo
        ee.Initialize(project=project)
        print(f"GEE inicializado correctamente (project={project}).")
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
            return
        # Si falla la autenticación, se avisa al usuario que revise su conexión a internet o permisos
        except Exception as e_final:
            print(f"ERROR: Error fatal iniciando GEE: {e_final}")
            print("Verifica que tengas permisos en el proyecto o conexión a internet.")
            raise

        
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
    
    Datos:
        - Origen: USGS/SRTMGL1_003
        - Formato de salida: .tif
        - Ciudad: Bounding box de Valdivia
        - Resolución exportada: 30m (nativa)
     
    Salida: 
        Archivo generado: data/raw/srtm_valdivia.tif 
    """
    print("\nIniciando descarga: SRTM (Topología)...")
    try:
        # Obtengo el bounding box de Valdivia que se usará para recortar la imagen
        roi = get_roi()
        # Carga imagen SRTM 30m desde GEE y la recorta a Valdivia
        image = ee.Image("USGS/SRTMGL1_003").clip(roi) # Dataset SRTM 30m
        # Ruta donde se guardará el archivo TIFF exportado: data/raw/srtm_valdivia.tif
        filename = os.path.join(DATA_RAW_PATH, "srtm_valdivia.tif")
        # Exporta la imagen al disco local usando geemap
        geemap.ee_export_image(image, filename=filename, scale=30, region=roi)
        print(f"EXITO: SRTM descargado en: {filename}")
    except Exception as e: # En caso de error, se muestra mensaje de fallo
        print(f"ERROR: Error descargando SRTM: {e}")

def download_sentinel2():
    """
    Descarga datos de vegetación (Sentinel-2) de verano con baja nubosidad.
    
    Descripción:
        Busca imágenes de la colección Sentinel-2 para el verano de 2024, filtrando por baja 
        nubosidad (<10%), seleccionando la imagen más limpia, recortando a la zona de interés 
        y exportando las bandas B4, B8, B3 y B2.

    Salida: 
        Archivo generado: data/raw/sentinel2_valdivia.tif
    """
    print("\nIniciando descarga: Sentinel-2 (Vegetación)...")
    try:
        roi = get_roi() # Obtengo la bounding box de recorte (de Valdivia)
        # Filtramos por fecha de verano (temporada incendios) y pocas nubes
        # se ordena por nubosidad
        image = (ee.ImageCollection('COPERNICUS/S2_SR')
                 .filterBounds(roi)
                 .filterDate('2024-01-01', '2024-03-01')
                 .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 10))
                 .sort('CLOUDY_PIXEL_PERCENTAGE') # Ordena por menos nubes
                 .first()                         # Toma la imagen más limpia
                 .clip(roi))
        # Si no hay imágenes sin nubes, se informa
        if image is None:
            print("ADVERTENCIA: No se encontraron imágenes Sentinel-2 sin nubes.")
            return
        # Se genera ruta de salida para la descarga: data/raw/sentinel2_valdivia.tif        
        filename = os.path.join(DATA_RAW_PATH, "sentinel2_valdivia.tif")
        # Descargamos bandas clave para NDVI (B4=Red, B8=NIR) y Visual (B2=Azul, B3=Verde)       
        # Scale 10m es la resolución nativa de Sentinel
        geemap.ee_export_image(image.select(['B4', 'B8', 'B3', 'B2']), 
                               filename=filename, scale=10, region=roi)
        print(f"EXITO: Sentinel-2 descargado en: {filename}")
    except Exception as e: # En caso de error, se muestra mensaje de fallo
        print(f"ERROR: Error descargando Sentinel-2: {e}")

def download_era5():
    """
    Descarga promedio mensual de viento ERA5-Land.
    
    Descripción:
        Obtiene datos horarios de ERA5-Land, calculando el promedio mensual de las componentes 
        del viento (U y V) para el verano de 2024 a 10m de altura, y exporta el resultado 
        con un reescalado a 1000 metros (1km).

    Salida:
        Archivo generado: 'data/raw/era5_wind_valdivia.tif'.
    """
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
        filename = os.path.join(DATA_RAW_PATH, "era5_wind_valdivia.tif")
        # ERA5 tiene baja resolución (11km), pero exportamos a 100m para suavizar
        # Exporta con resolución "suavizada" (1000m)
        geemap.ee_export_image(image, filename=filename, scale=1000, region=roi)
        print(f"EXITO: ERA5 (Viento) descargado en: {filename}")
    except Exception as e: # En caso de error, se muestra mensaje de fallo
        print(f"ERROR: Error descargando ERA5: {e}")

def download_pangaea():
    """
    Descarga datos históricos de incendios (Pangaea ZIP).

    Descripción:
        Realiza una petición HTTP GET para descargar un archivo ZIP desde el repositorio 
        de la página de Pangaea, el cual contiene shapefiles de cicatrices de incendios (FireScar) 
        para la Región de Los Ríos. Y se descomprime el contenido automáticamente.
    
    Salida: 
        Carpeta generada: data/raw/incendios_pangaea/ y su contenido descomprimido.
    """
    print("\nIniciando descarga: Incendios Históricos (Pangaea)...")
    # URL directa del ZIP del dataset de Los Ríos (región actual de Valdivia)
    # en esta URL está el registro histórico de incendios para Los Ríos, por parte de la CONAF
    direct_zip_url = "https://download.pangaea.de/dataset/941127/files/FireScar_CL-LR_LosRios_1985-2018.zip"
    try: # Solicita el ZIP desde internet
        response = requests.get(direct_zip_url)
        if response.status_code == 200: # Si la descarga fue exitosa (200), se procesa el ZIP
            z = zipfile.ZipFile(io.BytesIO(response.content)) # Carga ZIP en memoria
            extract_path = os.path.join(DATA_RAW_PATH, "incendios_pangaea")
            z.extractall(extract_path) # Extrae contenido del ZIP
            print(f"EXITO: ZIP Pangaea descargado y extraído en: {extract_path}")
        else: # En caso de fallo, se avisa al usuario para descarga manual
            print(f"ADVERTENCIA: No se pudo descargar automáticamente (Status {response.status_code}).")
            print(f"Por favor descarga manual: {direct_zip_url}")
    except Exception as e:
        print(f"ERROR: Error en descarga Pangaea: {e}")

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
        'conaf': download_conaf # amenaza y riesgo de incendios
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
    gee_needed = any(s in ['srtm', 'sentinel2', 'era5'] for s in sources_to_run)
    if gee_needed:
        init_gee()

    # Ejecutar descargas
    print("="*40)
    print(f"Iniciando pipeline para: {', '.join(sources_to_run)}")
    print("="*40)
    # Ejecuta cada descarga solicitada
    for source in sources_to_run:
        available_sources[source]()
    print("\nProceso finalizado.") # Mensaje de proceso finalizado

# Ejecuta main() solo si el script se corre directamente
if __name__ == "__main__":
    main()