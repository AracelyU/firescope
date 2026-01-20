"""
Aplicación web.
"""
import pandas as pd
import streamlit as st
import plotly.express as px

# Configuración de la página
st.set_page_config(
    page_title="Análisis Territorial - Laboratorio Integrador",
    page_icon="🗺️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# CSS personalizado
st.markdown("""
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
    </style>
""", unsafe_allow_html=True)

# Título principal
st.title("🗺️ Sistema de Análisis Territorial")

# Sidebar
with st.sidebar:
    st.image("https://registro.usach.cl/imagen/UsachP2.png", width=150)
    st.markdown("---")

    st.markdown("### 📊 Navegación")
    page = st.selectbox(
        "Seleccione una sección:",
        ["🏠 Inicio", "📊 Datos", "🗺️ Análisis Espacial", "📈 Resultados"]
    )

    st.markdown("---")
    st.markdown("### ℹ️ Información")
    st.info(
        """
        **Laboratorio Integrador**

        Geoinformática 2025

        USACH
        """
    )

# Contenido principal según página seleccionada
if page == "🏠 Inicio":
    # inicio
    print("inicio")

elif page == "📊 Datos":
    # datos
    print("datos")

elif page == "🗺️ Análisis Espacial":
    # analisis
    print("analisis espacial")

elif page == "📈 Resultados":
    st.header("📈 Resultados de la Simulación")
    st.markdown("A continuación se presentan los resultados visuales y estadísticos del modelo de propagación.")

    # Crear dos columnas para organizar el layout
    col1, col2 = st.columns([1, 1])

    with col1:
        st.subheader("Visualización del Incendio")
        # Mostramos el video generado
        video_path = "outputs/maps/simulacion.mp4"
        try:
            st.video(video_path)
            st.caption("Evolución espacial del fuego sobre Valdivia (Autómata Celular).")
        except FileNotFoundError:
            st.error("⚠️ El video de simulación no se ha generado aún.")

    with col2:
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

# Footer
st.markdown("---")
st.markdown(
    """
    <div style='text-align: center'>
        <p>Desarrollado para el curso de Geoinformática - USACH 2025</p>
        <p>Prof. Francisco Parra O. | <a href='mailto:francisco.parra.o@usach.cl'>francisco.parra.o@usach.cl</a></p>
    </div>
    """,
    unsafe_allow_html=True
)

col_left, col_right = st.columns([2, 1])

with col_left:
    st.video("outputs/maps/simulacion.mp4")

with col_right:
    st.markdown("### Parámetros de la simulación")
