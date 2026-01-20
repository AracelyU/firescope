import streamlit as st
import numpy as np
import rasterio
import imageio
import plotly.graph_objects as go
import pandas as pd
import plotly.express as px


T = 200

@st.cache_data
def cargar_simulacion():
    return np.array([
        imageio.imread(f"outputs/maps/simulacion/{t}.png")[::4, ::4] for t in range(T) 
    ])

@st.cache_data
def cargar_topologia():
    return rasterio.open("data/processed/topologia_processed.tif").read(1)[::4,::4]


simulaciones = cargar_simulacion()
topologia = cargar_topologia()

WIDTH = 484
HEIGHT = 521

MIN_LON, MAX_LON = -71.8, -70.8
MIN_LAT, MAX_LAT = -33.8, -32.8

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
