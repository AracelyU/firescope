import os
import glob
import numpy as np
import rasterio
from rasterio.warp import calculate_default_transform, reproject, Resampling
from rasterio.features import rasterize
import geopandas as gpd
import pandas as pd
from shapely.geometry import box
import re # Para buscar la fecha en el nombre del archivo

# --- CONFIGURACIÓN DE RUTAS ---
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_DIR = os.path.join(BASE_DIR, "data", "raw")
PROCESSED_DIR = os.path.join(BASE_DIR, "data", "processed")
REF_RASTER = os.path.join(RAW_DIR, "srtm_valdivia.tif") 

def get_reference_meta():
    """Obtiene metadata del raster maestro (Altura)."""
    with rasterio.open(REF_RASTER) as src:
        return src.meta.copy(), src.read(1), src.bounds

def align_raster(source_path, output_name, fill_value=0):
    """Alinea cualquier raster al maestro."""
    if not os.path.exists(source_path):
        print(f"⚠️  Saltando {output_name}: No existe {os.path.basename(source_path)}")
        return

    dst_meta, _, dst_bounds = get_reference_meta()
    output_path = os.path.join(PROCESSED_DIR, output_name)

    with rasterio.open(source_path) as src:
        transform, width, height = calculate_default_transform(
            src.crs, dst_meta['crs'], dst_meta['width'], dst_meta['height'], *dst_bounds
        )

        dst_meta.update({
            'crs': dst_meta['crs'],
            'transform': transform,
            'width': width,
            'height': height,
            'nodata': fill_value,
            'dtype': 'float32'
        })

        destination = np.zeros((height, width), dtype='float32')

        reproject(
            source=rasterio.band(src, 1),
            destination=destination,
            src_transform=src.transform,
            src_crs=src.crs,
            dst_transform=transform,
            dst_crs=dst_meta['crs'],
            resampling=Resampling.bilinear
        )

        with rasterio.open(output_path, 'w', **dst_meta) as dst:
            dst.write(destination, 1)

    print(f"✅ Raster procesado: {output_name}")

def extract_date_from_filename(filename):
    """Intenta extraer una fecha (YYYYMMDD) del nombre del archivo."""
    match = re.search(r'(\d{8})', filename)
    if match:
        return int(match.group(1))
    return 0

def process_fires(cumulative_output="grid_incendios_historicos.tif", recent_output="grid_incendio_reciente.tif"):
    """
    Genera DOS archivos:
    1. Acumulado histórico (suma de todos).
    2. El más reciente encontrado (para simulación).
    """
    pangaea_dir = os.path.join(RAW_DIR, "incendios_pangaea")
    print(f"\n🔍 Buscando incendios en: {pangaea_dir} ...")

    all_shps = []
    for root, dirs, files in os.walk(pangaea_dir):
        for file in files:
            if file.startswith("FireScar") and file.endswith(".shp"):
                all_shps.append(os.path.join(root, file))

    if not all_shps:
        print("❌ No se encontraron archivos shapefile.")
        return

    dst_meta, _, dst_bounds = get_reference_meta()
    bbox_valdivia = box(*dst_bounds)
    
    # Lista para guardar tuplas: (fecha, geodataframe, nombre_archivo)
    valid_fires = []

    print(f"   Analizando {len(all_shps)} archivos...")
    
    for shp_path in all_shps:
        try:
            gdf = gpd.read_file(shp_path)
            if gdf.crs != dst_meta['crs']:
                gdf = gdf.to_crs(dst_meta['crs'])

            # Verificar intersección
            if gdf.intersects(bbox_valdivia).any():
                gdf_clipped = gdf[gdf.intersects(bbox_valdivia)]
                if not gdf_clipped.empty:
                    # Extraer fecha para ordenar
                    date_num = extract_date_from_filename(os.path.basename(shp_path))
                    valid_fires.append((date_num, gdf_clipped, os.path.basename(shp_path)))
                    print(f"   🔥 MATCH ({date_num}): {os.path.basename(shp_path)}")
                
        except Exception as e:
            pass

    if not valid_fires:
        print("⚠️  Ningún incendio cae en Valdivia. Generando rasters vacíos.")
        empty_arr = np.zeros((dst_meta['height'], dst_meta['width']), dtype=rasterio.uint8)
        dst_meta.update({'dtype': 'uint8', 'nodata': 0, 'count': 1})
        
        with rasterio.open(os.path.join(PROCESSED_DIR, cumulative_output), 'w', **dst_meta) as dst:
            dst.write(empty_arr, 1)
        with rasterio.open(os.path.join(PROCESSED_DIR, recent_output), 'w', **dst_meta) as dst:
            dst.write(empty_arr, 1)
        return

    # --- 1. GENERAR ACUMULADO (HISTÓRICO) ---
    print(f"\n   📊 Generando mapa acumulado de {len(valid_fires)} incendios...")
    # Concatenar todos los GDFs
    all_gdfs = pd.concat([f[1] for f in valid_fires], ignore_index=True)
    
    shapes_all = ((geom, 1) for geom in all_gdfs.geometry)
    raster_all = rasterize(
        shapes=shapes_all,
        out_shape=(dst_meta['height'], dst_meta['width']),
        transform=dst_meta['transform'],
        fill=0,
        dtype=rasterio.uint8
    )
    
    dst_meta.update({'dtype': 'uint8', 'nodata': 0, 'count': 1})
    with rasterio.open(os.path.join(PROCESSED_DIR, cumulative_output), 'w', **dst_meta) as dst:
        dst.write(raster_all, 1)
    print(f"✅ Guardado: {cumulative_output}")

    # --- 2. GENERAR RECIENTE (SIMULACIÓN) ---
    # Ordenamos por fecha (el primer elemento de la tupla) de mayor a menor
    valid_fires.sort(key=lambda x: x[0], reverse=True)
    
    latest_date, latest_gdf, latest_name = valid_fires[0]
    print(f"\n   🕒 Incendio más reciente: {latest_name} (Fecha: {latest_date})")
    
    shapes_recent = ((geom, 1) for geom in latest_gdf.geometry)
    raster_recent = rasterize(
        shapes=shapes_recent,
        out_shape=(dst_meta['height'], dst_meta['width']),
        transform=dst_meta['transform'],
        fill=0,
        dtype=rasterio.uint8
    )
    
    with rasterio.open(os.path.join(PROCESSED_DIR, recent_output), 'w', **dst_meta) as dst:
        dst.write(raster_recent, 1)
    print(f"✅ Guardado: {recent_output}")

def main():
    if not os.path.exists(PROCESSED_DIR):
        os.makedirs(PROCESSED_DIR)

    print("🔄 --- INICIANDO PREPROCESAMIENTO ---")

    # 1. Capas Base
    align_raster(REF_RASTER, "grid_altura.tif")
    align_raster(os.path.join(RAW_DIR, "sentinel2_valdivia.tif"), "grid_vegetacion.tif")
    align_raster(os.path.join(RAW_DIR, "era5_wind_valdivia.tif"), "grid_viento.tif")
    
    # 2. Capas CONAF
    align_raster(os.path.join(RAW_DIR, "conaf_amenaza", "raster", "14_amenaza.tif"), "grid_amenaza.tif")
    align_raster(os.path.join(RAW_DIR, "conaf_riesgo", "raster", "14_riesgo.tif"), "grid_riesgo.tif")

    # 3. INCENDIOS (Doble estrategia)
    process_fires(cumulative_output="grid_incendios_historicos.tif", 
                  recent_output="grid_incendio_reciente.tif")

    print("\n✨ Preprocesamiento finalizado.")

if __name__ == "__main__":
    main()