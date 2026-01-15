"""
Aplicación web.
"""

import streamlit as st

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
    print("resultados")

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
