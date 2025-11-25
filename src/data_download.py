import os
import argparse
import requests
import zipfile
import io
import sys
import ee
import geemap
import gdown

# --- CONFIGURACIÓN GLOBAL ---
# Coordenadas de Valdivia, Región de Los Ríos (Bounding Box aproximado)
# [Oeste, Sur, Este, Norte]
VALDIVIA_BBOX = [-73.30, -39.88, -73.16, -39.75]
DATA_RAW_PATH = os.path.join("data", "raw")

# CONSTANTE GLOBAL: El ID de proyecto compartido
# Esto permite correr el script sin configurar nada extra.
DEFAULT_GEE_PROJECT = "composed-augury-451119-b6"

def init_gee():
    """
    Inicializa Google Earth Engine.
    Prioridad de autenticación:
    1. Variable de entorno (si el usuario experto configuró la suya).
    2. Proyecto por defecto del equipo (para compañeros/profesor).
    3. Autenticación interactiva si falla lo anterior.
    """
    # 1. Intentar con variable de entorno (Best Practice para expertos)
    project = os.environ.get('GOOGLE_CLOUD_PROJECT') or os.environ.get('EE_PROJECT')
    
    # 2. Si no hay variable, usar el ID del equipo
    if not project:
        project = DEFAULT_GEE_PROJECT

    try:
        # Intentamos inicializar directo
        ee.Initialize(project=project)
        print(f"✅ GEE inicializado correctamente (project={project}).")
        return

    except Exception:
        print(f"⚠️ Credenciales no encontradas o expiradas para el proyecto {project}.")
        print("⚠️ Iniciando autenticación interactiva (sigue las instrucciones en el navegador)...")
        
        try:
            # Fuerza la autenticación
            ee.Authenticate()
            # Reintenta inicializar con tu proyecto después de autenticar
            ee.Initialize(project=project)
            print(f"✅ GEE inicializado y autenticado exitosamente (project={project}).")
            return
            
        except Exception as e_final:
            print(f"❌ Error fatal iniciando GEE: {e_final}")
            print("👉 Verifica que tengas permisos en el proyecto o conexión a internet.")
            raise

        
def get_roi():
    """Retorna la geometría de la zona de estudio (Valdivia)."""
    return ee.Geometry.Rectangle(VALDIVIA_BBOX)

# --- FUNCIONES DE DESCARGA ---

def download_srtm():
    """Descarga datos de topología (SRTM) - Altura."""
    print("\n⬇️  Iniciando descarga: SRTM (Topología)...")
    try:
        roi = get_roi()
        # Dataset SRTM 30m
        image = ee.Image("USGS/SRTMGL1_003").clip(roi)
        
        filename = os.path.join(DATA_RAW_PATH, "srtm_valdivia.tif")
        geemap.ee_export_image(image, filename=filename, scale=30, region=roi)
        print(f"✅ SRTM descargado en: {filename}")
    except Exception as e:
        print(f"❌ Error descargando SRTM: {e}")

def download_sentinel2():
    """Descarga datos de vegetación (Sentinel-2)."""
    print("\n⬇️  Iniciando descarga: Sentinel-2 (Vegetación)...")
    try:
        roi = get_roi()
        # Filtramos por fecha de verano (temporada incendios) y pocas nubes
        image = (ee.ImageCollection('COPERNICUS/S2_SR')
                 .filterBounds(roi)
                 .filterDate('2024-01-01', '2024-03-01')
                 .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 10))
                 .sort('CLOUDY_PIXEL_PERCENTAGE')
                 .first()
                 .clip(roi))
        
        if image is None:
            print("⚠️ No se encontraron imágenes Sentinel-2 sin nubes.")
            return

        # Descargamos bandas clave para NDVI (B4=Red, B8=NIR) y Visual (B2, B3)
        filename = os.path.join(DATA_RAW_PATH, "sentinel2_valdivia.tif")
        # Scale 10m es la resolución nativa de Sentinel
        geemap.ee_export_image(image.select(['B4', 'B8', 'B3', 'B2']), 
                               filename=filename, scale=10, region=roi)
        print(f"✅ Sentinel-2 descargado en: {filename}")
    except Exception as e:
        print(f"❌ Error descargando Sentinel-2: {e}")

def download_era5():
    """Descarga datos de Viento (ERA5-Land)."""
    print("\n⬇️  Iniciando descarga: ERA5 (Viento)...")
    try:
        roi = get_roi()
        # ERA5 Land Hourly - Filtramos un promedio del verano para el modelo base
        # Seleccionamos componentes U y V del viento a 10m de altura
        collection = (ee.ImageCollection("ECMWF/ERA5_LAND/HOURLY")
                      .filterBounds(roi)
                      .filterDate('2024-01-01', '2024-02-01')
                      .select(['u_component_of_wind_10m', 'v_component_of_wind_10m']))
        
        # Reducimos a un promedio temporal para tener una "imagen" base del viento predominante
        image = collection.mean().clip(roi)
        
        filename = os.path.join(DATA_RAW_PATH, "era5_wind_valdivia.tif")
        # ERA5 tiene baja resolución (11km), pero exportamos a 100m para suavizar
        geemap.ee_export_image(image, filename=filename, scale=1000, region=roi)
        print(f"✅ ERA5 (Viento) descargado en: {filename}")
    except Exception as e:
        print(f"❌ Error descargando ERA5: {e}")

def download_pangaea():
    """Descarga datos históricos de incendios (Pangaea ZIP)."""
    print("\n⬇️  Iniciando descarga: Incendios Históricos (Pangaea)...")
    url = "https://doi.pangaea.de/10.1594/PANGAEA.941127?format=html#download" # Enlace base ref
    # Nota: El enlace directo al ZIP específico suele ser dinámico o requerir scraping.
    # Usaremos el enlace directo al archivo ZIP mencionado "LosLagos" si es estático, 
    # si no, descargaremos el dataset principal o dejaremos instrucciones.
    
    # Enlace directo reconstruido para el archivo de Los Lagos (donde estaba Valdivia antes)
    # Si este enlace falla por cambios en el servidor, usar el genérico.
    direct_zip_url = "https://download.pangaea.de/dataset/941127/files/FireScar_CL-LR_LosRios_1985-2018.zip"
    
    try:
        response = requests.get(direct_zip_url)
        if response.status_code == 200:
            z = zipfile.ZipFile(io.BytesIO(response.content))
            extract_path = os.path.join(DATA_RAW_PATH, "incendios_pangaea")
            z.extractall(extract_path)
            print(f"✅ ZIP Pangaea descargado y extraído en: {extract_path}")
        else:
            print(f"⚠️ No se pudo descargar automáticamente (Status {response.status_code}).")
            print(f"👉 Por favor descarga manual: {direct_zip_url}")
    except Exception as e:
        print(f"❌ Error en descarga Pangaea: {e}")

def download_conaf():
    """
    Descarga SOLO las subcarpetas de la Región 14 (Los Ríos) desde CONAF.
    Evita descargar terabytes de datos de otras regiones.
    """
    print("\n⬇️  Iniciando descarga: CONAF (Solo Región 14 - Los Ríos)...")
    
    try:
        import gdown
    except ImportError:
        print("❌ Error: Falta librería gdown. Ejecuta: pip install gdown")
        return

    # IDs extraídos de los enlaces que proporcionaste
    carpetas_target = {
        "Amenaza_Raster": {
            "id": "1xc8qTlR6WsFtO4bt5gth_H3p0ENtJCK1",  
            "path": os.path.join(DATA_RAW_PATH, "conaf_amenaza", "raster")
        },
        "Amenaza_Shapefile": {
            "id": "1EkwZdg0lUUruyEDPau_Gpa6W--4PI2NQ", 
            "path": os.path.join(DATA_RAW_PATH, "conaf_amenaza", "shapefiles")
        },
        "Riesgo_Raster": {
            "id": "1j3nKVJuwi04gjlbiSmEbRWmyJkZRIM9Z", # ID NUEVO (Riesgo Raster)
            "path": os.path.join(DATA_RAW_PATH, "conaf_riesgo", "raster")
        },
        "Riesgo_Shapefile": {
            "id": "1zywr5_DbGmtm0sYZSS3i75yivuP1QGPK", # ID NUEVO (Riesgo Shapefile)
            "path": os.path.join(DATA_RAW_PATH, "conaf_riesgo", "shapefiles")
        }
    }

    for nombre, info in carpetas_target.items():
        print(f"   👉 Descargando {nombre} (Valdivia)...")
        
        # Crear carpeta destino si no existe
        if not os.path.exists(info["path"]):
            os.makedirs(info["path"])
        
        try:
            # url format para gdown
            # CAMBIO CRÍTICO: Usar formato de 'folders' en lugar de 'uc?id'
            url = f'https://drive.google.com/drive/folders/{info["id"]}'

            # quiet=False para ver el progreso
            gdown.download_folder(url, output=info["path"], quiet=False, use_cookies=False)
            print(f"   ✅ {nombre} completado.")
        except Exception as e:
            print(f"   ❌ Error en {nombre}: {e}")

# --- GESTOR PRINCIPAL ---

def main():
    # Asegurar que existe la carpeta
    if not os.path.exists(DATA_RAW_PATH):
        os.makedirs(DATA_RAW_PATH)
        print(f"📂 Carpeta creada: {DATA_RAW_PATH}")

    parser = argparse.ArgumentParser(description="Script de descarga de datos geoespaciales para Firescope.")
    
    available_sources = {
        'srtm': download_srtm,
        'sentinel2': download_sentinel2,
        'era5': download_era5,
        'pangaea': download_pangaea,
        'conaf': download_conaf
    }
    
    parser.add_argument('--sources', nargs='+', required=True,
                        choices=list(available_sources.keys()) + ['all'],
                        help='Lista de fuentes a descargar (separadas por espacio) o "all".')

    args = parser.parse_args()
    
    sources_to_run = []
    if 'all' in args.sources:
        sources_to_run = list(available_sources.keys())
    else:
        sources_to_run = args.sources

    # Inicializar GEE solo si es necesario (para srtm, sentinel, era5)
    gee_needed = any(s in ['srtm', 'sentinel2', 'era5'] for s in sources_to_run)
    if gee_needed:
        init_gee()

    # Ejecutar descargas
    print("="*40)
    print(f"🚀 Iniciando pipeline para: {', '.join(sources_to_run)}")
    print("="*40)
    
    for source in sources_to_run:
        available_sources[source]()
        
    print("\n✨ Proceso finalizado.")

if __name__ == "__main__":
    main()