from pathlib import Path

import streamlit as st
import numpy as np
import rasterio
import folium
import streamlit.components.v1 as components
from rasterio.mask import mask
from rasterio.features import rasterize
from rasterio.transform import from_bounds
from rasterio.warp import Resampling, reproject, transform_bounds
import geopandas as gpd
import imageio
import plotly.graph_objects as go
import pandas as pd
import plotly.express as px


T = 400
down_sample = 3

@st.cache_data
def cargar_simulacion():
    return np.array([
        imageio.imread(f"outputs/maps/simulacion/{t}.png")[::down_sample, ::down_sample] for t in range(T) 
    ])

@st.cache_data
def cargar_topologia():
    return rasterio.open("data/processed/topologia_processed.tif").read(1)[::down_sample,::down_sample]

@st.cache_data
def obtener_bounds_topologia_4326():
    topo_path = "data/processed/topologia_processed.tif"
    with rasterio.open(topo_path) as src:
        left, bottom, right, top = src.bounds
        return transform_bounds(src.crs, "EPSG:4326", left, bottom, right, top)

@st.cache_data
def cargar_riesgo_resampleado(width, height, bounds):
    risk_tif = "data/raw/conaf_riesgo/raster/14_riesgo.tif"
    comuna_shp = "data/raw/comuna/comuna_valdivia.shp"
    if not Path(risk_tif).exists():
        raise FileNotFoundError(f"No se encontro: {risk_tif}")
    if not Path(comuna_shp).exists():
        raise FileNotFoundError(f"No se encontro: {comuna_shp}")

    comuna = gpd.read_file(comuna_shp)
    with rasterio.open(risk_tif) as src:
        poly = comuna.to_crs(src.crs)
        geoms = [geom for geom in poly.geometry if geom is not None]
        out_image, out_transform = mask(src, geoms, crop=True)
        out_meta = src.meta.copy()
        out_meta.update(
            {
                "height": out_image.shape[1],
                "width": out_image.shape[2],
                "transform": out_transform,
            }
        )

    dst = np.full((height, width), np.nan, dtype="float32")
    dst_transform = from_bounds(*bounds, width, height)
    reproject(
        source=out_image[0].astype("float32"),
        destination=dst,
        src_transform=out_meta["transform"],
        src_crs=out_meta["crs"],
        dst_transform=dst_transform,
        dst_crs="EPSG:4326",
        src_nodata=out_meta.get("nodata"),
        dst_nodata=np.nan,
        resampling=Resampling.nearest,
    )
    return dst

@st.cache_data
def obtener_bounds_comuna_4326():
    comuna_shp = "data/raw/comuna/comuna_valdivia.shp"
    if not Path(comuna_shp).exists():
        raise FileNotFoundError(f"No se encontro: {comuna_shp}")
    comuna = gpd.read_file(comuna_shp).to_crs("EPSG:4326")
    minx, miny, maxx, maxy = comuna.total_bounds
    return (minx, miny, maxx, maxy)

simulaciones = cargar_simulacion()
topologia = cargar_topologia()

WIDTH = 484
HEIGHT = 521

MIN_LON, MAX_LON, MIN_LAT, MAX_LAT = (-73.30, -73.16, -39.88, -39.75)

lons = np.linspace(MIN_LON, MAX_LON, WIDTH)
lats = np.linspace(MIN_LAT, MAX_LAT, HEIGHT)

col_left, col_right = st.columns([2, 1])

with col_left:
    fig = go.Figure(
        data=[
            go.Surface(
                x=lons,
                y=lats,
                z=topologia,
                surfacecolor=simulaciones[0],
                coloraxis="coloraxis",
            )
        ],
        frames=[
            go.Frame(
                data=[
                    go.Surface(
                        surfacecolor=simulaciones[t]
                    )
                ],
                name=str(t),
            )
            for t in range(T)
        ],
    )


    fig.update_layout(
        scene={
            "aspectmode": "manual",
            "aspectratio": {"x": 1, "y": 1, "z": 0.3},
            "xaxis_title": "Longitud",
            "yaxis_title": "Latitud",
            "zaxis_title": "Elevación",
            "camera": {
                "eye": {"x": 1., "y": 1., "z": 1}
            },
        },
        sliders=[{
            "steps": [
                {
                    "method": "animate",
                    "label": str(t),
                    "args": [[str(t)], {"mode": "immediate"}],
                }
                for t in range(T)
            ],
            "currentvalue": {"prefix": "Tiempo: "},
        }],
        updatemenus=[
            {
                "type": "buttons",
                "showactive": True,
                "buttons": [
                    {
                        "label": "▶ Play",
                        "method": "animate",
                        "args": [None, {"frame": {"duration": 0, "redraw": True}}],
                    },
                    {
                        "label": "⏸ Pause",
                        "method": "animate",
                        "args": [[None], {"mode": "immediate"}],
                    },
                ],
            }
        ],
        coloraxis=dict(
            colorscale="Viridis",
            cmin=0,
            cmax=2,
            colorbar=dict(
                title="Estado Incendio",
                thickness=30,
            ),
        )
    )

    st.subheader("Visualización del Incendio")
    st.plotly_chart(
        fig,
        width="stretch",
        config={
            "responsive": True,
            "scrollZoom": True,
            "displaylogo": False,
        },
    )

with col_right:
    st.subheader("Estadísticas de Propagación")
    # Cargamos el CSV generado en el notebook 03
    csv_path = "data/processed/stats_simulacion.csv"
    
    try:
        df = pd.read_csv(csv_path)
        
        # Crear gráfico interactivo con Plotly (Requisito del PDF: Gráfico 2)
        fig = px.line(df, x="Paso", y=["Area Quemada", "Fuego Activo"],
                        title="Curva de Crecimiento del Incendio",
                        labels={"value": "Celdas Afectadas", "variable": "Estado"},
                        color_discrete_map={"Area Quemada": "gray", "Fuego Activo": "red"})
        
        st.plotly_chart(fig, use_container_width=True)
        
        # Métricas clave (Extra points para el dashboard)
        max_fuego = df["Fuego Activo"].max()
        total_final = df["Area Quemada"].iloc[-1]
        
        m1, m2 = st.columns(2)
        m1.metric("Pico Máximo de Fuego", f"{max_fuego} celdas")
        m2.metric("Área Total Afectada", f"{total_final} celdas")
        
    except FileNotFoundError:
        st.warning("⚠️ No se encontraron los datos estadísticos. Ejecuta el notebook 03 primero.")

st.markdown("---")
st.subheader("Comparacion visual: simulacion vs riesgo CONAF (Valdivia)")

try:
    frame_idx = st.slider("Paso de simulacion para comparar", 0, T - 1, T - 1)
    sim_frame = simulaciones[frame_idx]
    if sim_frame.ndim == 3:
        sim_gray = sim_frame.mean(axis=2)
    else:
        sim_gray = sim_frame

    # Asumimos que cualquier valor > 0 indica area afectada
    burn_mask = sim_gray > 0

    sim_bounds = obtener_bounds_topologia_4326()
    h, w = burn_mask.shape

    comuna_bounds = obtener_bounds_comuna_4326()
    lon_span = comuna_bounds[2] - comuna_bounds[0]
    lat_span = comuna_bounds[3] - comuna_bounds[1]
    risk_w = 700
    risk_h = max(1, int(risk_w * lat_span / max(lon_span, 1e-6)))
    riesgo = cargar_riesgo_resampleado(risk_w, risk_h, comuna_bounds)

    comuna_shp = "data/raw/comuna/comuna_valdivia.shp"
    comuna = gpd.read_file(comuna_shp).to_crs("EPSG:4326")
    comuna_shapes = [(geom, 1) for geom in comuna.geometry if geom is not None]
    comuna_mask = rasterize(
        comuna_shapes,
        out_shape=(risk_h, risk_w),
        transform=from_bounds(*comuna_bounds, risk_w, risk_h),
        fill=0,
        dtype="uint8",
    )
    riesgo = np.where((comuna_mask == 1) & np.isnan(riesgo), 0, riesgo)

    # Mapa RGB del riesgo (0-4)
    risk_rgb = np.zeros((riesgo.shape[0], riesgo.shape[1], 3), dtype="uint8")
    class_colors = {
        0: (200, 200, 200),
        1: (181, 217, 168),
        2: (255, 235, 170),
        3: (255, 170, 85),
        4: (215, 48, 39),
    }
    for cls, color in class_colors.items():
        mask_cls = (riesgo == cls)
        risk_rgb[mask_cls] = color

    # Overlay de area quemada (RGBA) sobre el riesgo
    burn_rgba = np.zeros((h, w, 4), dtype="uint8")
    burn_rgba[..., 0] = 255
    burn_rgba[..., 3] = (burn_mask.astype("uint8") * 140)

    risk_rgba = np.zeros((riesgo.shape[0], riesgo.shape[1], 4), dtype="uint8")
    risk_rgba[..., :3] = risk_rgb
    risk_rgba[..., 3] = np.where(comuna_mask == 1, 200, 0).astype("uint8")

    risk_bounds = comuna_bounds
    burn_bounds = sim_bounds
    risk_bounds_latlon = [[risk_bounds[1], risk_bounds[0]], [risk_bounds[3], risk_bounds[2]]]
    burn_bounds_latlon = [[burn_bounds[1], burn_bounds[0]], [burn_bounds[3], burn_bounds[2]]]
    center_lat = (comuna_bounds[1] + comuna_bounds[3]) / 2
    center_lon = (comuna_bounds[0] + comuna_bounds[2]) / 2

    m = folium.Map(location=[center_lat, center_lon], zoom_start=11, tiles="CartoDB positron")
    folium.raster_layers.ImageOverlay(
        image=risk_rgba,
        bounds=risk_bounds_latlon,
        name="Riesgo CONAF",
        interactive=False,
        opacity=1.0,
        zindex=2,
    ).add_to(m)
    folium.raster_layers.ImageOverlay(
        image=burn_rgba,
        bounds=burn_bounds_latlon,
        name="Area quemada",
        interactive=False,
        opacity=1.0,
        zindex=3,
    ).add_to(m)
    folium.LayerControl(collapsed=True).add_to(m)

    st.caption("Mapa: riesgo CONAF + area quemada (rojo)")
    components.html(m.get_root().render(), height=520)

except FileNotFoundError as exc:
    st.warning(str(exc))
