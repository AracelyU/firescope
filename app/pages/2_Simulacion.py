import streamlit as st
import numpy as np
import rasterio
import imageio
import plotly.graph_objects as go


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
    st.markdown("### Datos de la simulación")
