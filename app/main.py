"""
Aplicacion web.
"""
from pathlib import Path

import folium
from folium.plugins import MousePosition
import geopandas as gpd
from matplotlib import colormaps
import numpy as np
import rasterio
from rasterio.features import rasterize
from rasterio.mask import mask
from rasterio.transform import array_bounds
from rasterio.warp import Resampling, calculate_default_transform, reproject
import streamlit as st
import streamlit.components.v1 as components

PROJECT_ROOT = Path(__file__).resolve().parents[1]

CLASS_COLORS = {
    0: (200, 200, 200),
    1: (181, 217, 168),
    2: (255, 235, 170),
    3: (255, 170, 85),
    4: (215, 48, 39),
}


def apply_comuna_mask(rgba, mask_arr):
    if mask_arr is None:
        return rgba
    rgba[~mask_arr] = [0, 0, 0, 0]
    return rgba


def risk_rgba_for_range(arr, rmin, rmax, mask_arr=None, opacity=0.85):
    h, w = arr.shape
    rgba = np.zeros((h, w, 4), dtype="uint8")

    for cls in range(rmin, rmax + 1):
        mask_cls = (arr == cls)
        r, g, b = CLASS_COLORS.get(cls, (0, 0, 0))
        rgba[mask_cls, 0] = r
        rgba[mask_cls, 1] = g
        rgba[mask_cls, 2] = b
        rgba[mask_cls, 3] = int(opacity * 255)

    rgba[np.isnan(arr)] = [0, 0, 0, 0]
    return apply_comuna_mask(rgba, mask_arr)


def continuous_rgba(arr, vmin, vmax, cmap_name, mask_arr=None, opacity=0.7):
    if vmin is None or vmax is None:
        return None
    arr_f = arr.astype("float32")
    valid = np.isfinite(arr_f)
    norm = (arr_f - vmin) / (vmax - vmin + 1e-6)
    norm = np.clip(norm, 0.0, 1.0)
    cmap = colormaps.get_cmap(cmap_name)
    rgba = (cmap(norm) * 255).astype("uint8")
    rgba[..., 3] = (valid * opacity * 255).astype("uint8")
    rgba[~valid] = [0, 0, 0, 0]
    return apply_comuna_mask(rgba, mask_arr)


def downsample_with_meta(arr2d, meta_4326, factor=3):
    arr_ds = arr2d[::factor, ::factor]
    t = meta_4326["transform"]
    meta_ds = meta_4326.copy()
    meta_ds["transform"] = rasterio.Affine(
        t.a * factor, t.b, t.c,
        t.d, t.e * factor, t.f
    )
    meta_ds["width"] = arr_ds.shape[1]
    meta_ds["height"] = arr_ds.shape[0]
    return arr_ds, meta_ds


def reproject_array_to_4326(arr2d, meta, resampling=Resampling.nearest):
    src_crs = meta["crs"]
    src_transform = meta["transform"]
    src_h, src_w = arr2d.shape
    left, bottom, right, top = array_bounds(src_h, src_w, src_transform)

    dst_crs = "EPSG:4326"
    dst_transform, dst_w, dst_h = calculate_default_transform(
        src_crs, dst_crs, src_w, src_h, left, bottom, right, top
    )

    dst = np.full((dst_h, dst_w), np.nan, dtype="float32")
    reproject(
        source=arr2d.astype("float32"),
        destination=dst,
        src_transform=src_transform,
        src_crs=src_crs,
        dst_transform=dst_transform,
        dst_crs=dst_crs,
        src_nodata=meta.get("nodata"),
        dst_nodata=np.nan,
        resampling=resampling,
    )

    meta_4326 = meta.copy()
    meta_4326.update(
        {
            "crs": rasterio.crs.CRS.from_string(dst_crs),
            "transform": dst_transform,
            "width": dst_w,
            "height": dst_h,
            "nodata": np.nan,
        }
    )
    return dst, meta_4326


def reproject_to_meta(arr2d, src_meta, dst_meta):
    dst = np.full((dst_meta["height"], dst_meta["width"]), np.nan, dtype="float32")
    reproject(
        source=arr2d.astype("float32"),
        destination=dst,
        src_transform=src_meta["transform"],
        src_crs=src_meta["crs"],
        dst_transform=dst_meta["transform"],
        dst_crs=dst_meta["crs"],
        src_nodata=src_meta.get("nodata"),
        dst_nodata=np.nan,
        resampling=Resampling.bilinear,
    )
    return dst


@st.cache_data(show_spinner=False)
def load_map_layers(project_root, downsample=3):
    project_root = Path(project_root)
    risk_tif = project_root / "data/raw/conaf_riesgo/raster/14_riesgo.tif"
    comuna_shp = project_root / "data/raw/comuna/comuna_valdivia.shp"
    s2_comuna = project_root / "data/raw/sentinel2_valdivia_comuna.tif"
    srtm_comuna = project_root / "data/raw/srtm_valdivia_comuna.tif"
    era5_comuna = project_root / "data/raw/era5_wind_valdivia_comuna.tif"

    if not risk_tif.exists():
        raise FileNotFoundError(f"No se encontro: {risk_tif}")
    if not comuna_shp.exists():
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
                "crs": src.crs,
                "nodata": src.nodata,
            }
        )

    data_4326, meta_4326 = reproject_array_to_4326(out_image[0], out_meta)
    data_ds, meta_ds = downsample_with_meta(data_4326, meta_4326, factor=downsample)

    left, bottom, right, top = array_bounds(
        meta_ds["height"], meta_ds["width"], meta_ds["transform"]
    )
    bounds = [[bottom, left], [top, right]]

    comuna_4326 = comuna.to_crs("EPSG:4326")
    comuna_mask_4326 = rasterize(
        [(geom, 1) for geom in comuna_4326.geometry if geom is not None],
        out_shape=(meta_4326["height"], meta_4326["width"]),
        transform=meta_4326["transform"],
        fill=0,
        dtype="uint8",
    )
    comuna_mask_ds, _ = downsample_with_meta(comuna_mask_4326, meta_4326, factor=downsample)
    comuna_mask_ds = comuna_mask_ds.astype(bool)

    ndvi_ds = elev_ds = slope_ds = wind_ds = None
    ndvi_vmin = ndvi_vmax = None
    elev_vmin = elev_vmax = None
    slope_vmin = slope_vmax = None
    wind_vmin = wind_vmax = None

    if s2_comuna.exists():
        with rasterio.open(s2_comuna) as src:
            data = src.read().astype("float32")
            s2_meta = src.meta.copy()
        red = data[0]
        nir = data[3]
        ndvi = (nir - red) / (nir + red + 1e-6)
        ndvi_4326 = reproject_to_meta(ndvi, s2_meta, meta_4326)
        ndvi_ds, _ = downsample_with_meta(ndvi_4326, meta_4326, factor=downsample)
        ndvi_vmin, ndvi_vmax = -1.0, 1.0

    if srtm_comuna.exists():
        with rasterio.open(srtm_comuna) as src:
            elev = src.read(1).astype("float32")
            srtm_meta = src.meta.copy()
        elev_4326 = reproject_to_meta(elev, srtm_meta, meta_4326)
        elev_ds, _ = downsample_with_meta(elev_4326, meta_4326, factor=downsample)
        elev_vmin, elev_vmax = np.nanpercentile(elev_ds, [2, 98])

        dy, dx = np.gradient(elev, srtm_meta["transform"][4], srtm_meta["transform"][0])
        slope = np.arctan(np.sqrt(dx**2 + dy**2)) * 180 / np.pi
        slope_4326 = reproject_to_meta(slope.astype("float32"), srtm_meta, meta_4326)
        slope_ds, _ = downsample_with_meta(slope_4326, meta_4326, factor=downsample)
        slope_vmin, slope_vmax = np.nanpercentile(slope_ds, [2, 98])

    if era5_comuna.exists():
        with rasterio.open(era5_comuna) as src:
            u = src.read(1).astype("float32")
            v = src.read(2).astype("float32")
            era5_meta = src.meta.copy()
        mag = np.sqrt(u**2 + v**2)
        wind_4326 = reproject_to_meta(mag, era5_meta, meta_4326)
        wind_ds, _ = downsample_with_meta(wind_4326, meta_4326, factor=downsample)
        wind_vmin, wind_vmax = np.nanpercentile(wind_ds, [2, 98])

    return {
        "risk_ds": data_ds,
        "bounds": bounds,
        "comuna": comuna_4326,
        "comuna_mask_ds": comuna_mask_ds,
        "ndvi_ds": ndvi_ds,
        "elev_ds": elev_ds,
        "slope_ds": slope_ds,
        "wind_ds": wind_ds,
        "ndvi_vmin": ndvi_vmin,
        "ndvi_vmax": ndvi_vmax,
        "elev_vmin": elev_vmin,
        "elev_vmax": elev_vmax,
        "slope_vmin": slope_vmin,
        "slope_vmax": slope_vmax,
        "wind_vmin": wind_vmin,
        "wind_vmax": wind_vmax,
    }


def build_map(layers, risk_range):
    risk_min, risk_max = risk_range
    bounds = layers["bounds"]

    center_lat = (bounds[0][0] + bounds[1][0]) / 2
    center_lon = (bounds[0][1] + bounds[1][1]) / 2

    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=11,
        tiles="CartoDB positron",
    )

    if layers["ndvi_ds"] is not None:
        ndvi_rgba = continuous_rgba(
            layers["ndvi_ds"],
            layers["ndvi_vmin"],
            layers["ndvi_vmax"],
            "RdYlGn",
            mask_arr=layers["comuna_mask_ds"],
            opacity=0.6,
        )
        folium.raster_layers.ImageOverlay(
            image=ndvi_rgba,
            bounds=bounds,
            name="Vegetacion NDVI",
            interactive=True,
            show=False,
            zindex=3,
        ).add_to(m)

    if layers["elev_ds"] is not None:
        elev_rgba = continuous_rgba(
            layers["elev_ds"],
            layers["elev_vmin"],
            layers["elev_vmax"],
            "terrain",
            mask_arr=layers["comuna_mask_ds"],
            opacity=0.6,
        )
        folium.raster_layers.ImageOverlay(
            image=elev_rgba,
            bounds=bounds,
            name="Elevacion",
            interactive=True,
            show=False,
            zindex=3,
        ).add_to(m)

    if layers["slope_ds"] is not None:
        slope_rgba = continuous_rgba(
            layers["slope_ds"],
            layers["slope_vmin"],
            layers["slope_vmax"],
            "magma",
            mask_arr=layers["comuna_mask_ds"],
            opacity=0.6,
        )
        folium.raster_layers.ImageOverlay(
            image=slope_rgba,
            bounds=bounds,
            name="Pendiente",
            interactive=True,
            show=False,
            zindex=3,
        ).add_to(m)

    if layers["wind_ds"] is not None:
        wind_rgba = continuous_rgba(
            layers["wind_ds"],
            layers["wind_vmin"],
            layers["wind_vmax"],
            "viridis",
            mask_arr=layers["comuna_mask_ds"],
            opacity=0.6,
        )
        folium.raster_layers.ImageOverlay(
            image=wind_rgba,
            bounds=bounds,
            name="Viento (magnitud)",
            interactive=True,
            show=False,
            zindex=3,
        ).add_to(m)

    risk_rgba = risk_rgba_for_range(
        layers["risk_ds"],
        risk_min,
        risk_max,
        mask_arr=layers["comuna_mask_ds"],
        opacity=0.85,
    )
    folium.raster_layers.ImageOverlay(
        image=risk_rgba,
        bounds=bounds,
        name=f"Riesgo [{risk_min}-{risk_max}]",
        interactive=True,
        zindex=6,
    ).add_to(m)

    border_fg = folium.FeatureGroup(name="Limite comunal", control=False)
    folium.GeoJson(
        layers["comuna"],
        style_function=lambda x: {"color": "black", "weight": 2, "fillOpacity": 0},
    ).add_to(border_fg)
    border_fg.add_to(m)

    folium.LayerControl(collapsed=False).add_to(m)
    MousePosition(prefix="Lat, Lon").add_to(m)

    return m


def fmt_range(vmin, vmax):
    if vmin is None or vmax is None:
        return "n/a"
    if not np.isfinite(vmin) or not np.isfinite(vmax):
        return "n/a"
    return f"{vmin:.1f} - {vmax:.1f}"


st.set_page_config(
    page_title="Analisis Territorial - Laboratorio Integrador",
    page_icon="",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    .main {
        padding-top: 2rem;
    }
    .stButton>button {
        background-color: #0066CC;
        color: white;
    }
    .st-emotion-cache-16idsys p {
        font-size: 1.1rem;
    }
    .legend-box {
        background: #11151d;
        border: 1px solid #2a3140;
        border-radius: 8px;
        padding: 12px;
        margin-bottom: 12px;
        color: #e6e6e6;
        font-size: 12px;
    }
    .legend-title {
        font-weight: 600;
        margin-bottom: 6px;
        font-size: 13px;
    }
    .legend-row span {
        display: inline-block;
        width: 12px;
        height: 12px;
        margin-right: 6px;
        border-radius: 2px;
    }
    .legend-gradient {
        height: 10px;
        border-radius: 999px;
        margin: 6px 0;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("Sistema de Analisis Territorial")

with st.sidebar:
    st.image("https://registro.usach.cl/imagen/UsachP2.png", width=150)
    st.markdown("---")
    st.markdown("### Informacion")
    st.info(
        """
        **Laboratorio Integrador**

        Geoinformatica 2025

        USACH
        """
    )

st.header("Mapa interactivo")
st.markdown(
    "Mapa de riesgo CONAF con capas extra (NDVI, elevacion, pendiente y viento)."
)

risk_range = st.slider(
    "Rango de riesgo (0 = muy bajo, 4 = muy alto)",
    min_value=0,
    max_value=4,
    value=(1, 4),
    step=1,
)

try:
    with st.spinner("Cargando mapa..."):
        layers = load_map_layers(str(PROJECT_ROOT), downsample=3)
    col_map, col_legend = st.columns([3, 1], gap="large")
    with col_map:
        folium_map = build_map(layers, risk_range)
        components.html(folium_map.get_root().render(), height=700)
        st.caption("Activa o desactiva capas en el panel de control del mapa.")
    with col_legend:
        st.markdown(
            f"""
            <div class="legend-box">
                <div class="legend-title">Riesgo incendios (CONAF)</div>
                <div class="legend-row"><span style="background:#d7d7d7;"></span>Muy bajo (0)</div>
                <div class="legend-row"><span style="background:#b5d9a8;"></span>Bajo (1)</div>
                <div class="legend-row"><span style="background:#ffebaa;"></span>Medio (2)</div>
                <div class="legend-row"><span style="background:#ffaa55;"></span>Alto (3)</div>
                <div class="legend-row"><span style="background:#d73027;"></span>Muy alto (4)</div>
                <div style="margin-top:6px;">Rango actual: {risk_range[0]} - {risk_range[1]}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        if layers["ndvi_ds"] is not None:
            st.markdown(
                """
                <div class="legend-box">
                    <div class="legend-title">Vegetacion NDVI</div>
                    <div class="legend-gradient" style="background: linear-gradient(to right, #d73027, #fdae61, #ffffbf, #a6d96a, #1a9850);"></div>
                    <div>-1.0 a 1.0</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        if layers["elev_ds"] is not None:
            st.markdown(
                f"""
                <div class="legend-box">
                    <div class="legend-title">Elevacion</div>
                    <div class="legend-gradient" style="background: linear-gradient(to right, #2b83ba, #abdda4, #ffffbf, #fdae61, #d7191c);"></div>
                    <div>{fmt_range(layers["elev_vmin"], layers["elev_vmax"])}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        if layers["slope_ds"] is not None:
            st.markdown(
                f"""
                <div class="legend-box">
                    <div class="legend-title">Pendiente</div>
                    <div class="legend-gradient" style="background: linear-gradient(to right, #000004, #3b0f70, #8c2981, #de4968, #fe9f6d, #fcfdbf);"></div>
                    <div>{fmt_range(layers["slope_vmin"], layers["slope_vmax"])}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        if layers["wind_ds"] is not None:
            st.markdown(
                f"""
                <div class="legend-box">
                    <div class="legend-title">Viento (magnitud)</div>
                    <div class="legend-gradient" style="background: linear-gradient(to right, #440154, #31688e, #35b779, #fde725);"></div>
                    <div>{fmt_range(layers["wind_vmin"], layers["wind_vmax"])}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
except FileNotFoundError as exc:
    st.error(str(exc))
except Exception as exc:
    st.error(f"Error cargando el mapa: {exc}")

st.markdown("---")
st.markdown(
    """
    <div style='text-align: center'>
        <p>Desarrollado para el curso de Geoinformatica - USACH 2025</p>
        <p>Prof. Francisco Parra O. | <a href='mailto:francisco.parra.o@usach.cl'>francisco.parra.o@usach.cl</a></p>
    </div>
    """,
    unsafe_allow_html=True,
)
