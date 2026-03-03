import streamlit as st
import hatanaka
import os
import re
import math
import pyproj
import rasterio
import requests
from pathlib import Path

# --- 1. CONFIGURACIÓN Y ESTILO ---
st.set_page_config(page_title="PPK Drone Geotools", page_icon="🛰️", layout="wide")

def local_css():
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@300;400;500;700&display=swap');

    /* Variables Globales Basadas en tu Web */
    :root {
        --azul-profundo: #142032;
        --verde-lima: #8CC63F;
        --gris-tecnico: #4D4D4D;
        --blanco: #FFFFFF;
        --fondo-gris: #F4F7F9;
    }

    /* Estilos Base de Streamlit */
    .stApp {
        font-family: 'Montserrat', sans-serif;
        background-color: var(--blanco);
    }

    /* Personalización de Headers (Basado en tu .hero-banner) */
    .custom-header {
        background-color: var(--azul-profundo);
        padding: 30px 20px;
        text-align: center;
        border-bottom: 5px solid var(--verde-lima);
        color: var(--blanco);
        margin-bottom: 30px;
        border-radius: 0 0 10px 10px;
    }
    .custom-header h1 {
        font-weight: 700;
        text-transform: uppercase;
        color: var(--blanco) !important;
        font-size: 2rem !important;
    }
    .custom-header strong { color: var(--verde-lima); }

    /* Estilo de Botones (Basado en tu .cta-whatsapp) */
    .stButton>button {
        background-color: var(--verde-lima) !important;
        color: var(--azul-profundo) !important;
        font-weight: 700 !important;
        border-radius: 50px !important;
        border: none !important;
        padding: 10px 25px !important;
        transition: 0.3s !important;
        text-transform: uppercase;
    }
    .stButton>button:hover {
        transform: scale(1.05);
        box-shadow: 0 4px 15px rgba(140, 198, 63, 0.4);
    }

    /* Estilo de Pestañas (Tabs) */
    .stTabs [data-baseweb="tab-list"] {
        gap: 10px;
        background-color: var(--fondo-gris);
        padding: 10px;
        border-radius: 10px;
    }
    .stTabs [data-baseweb="tab"] {
        height: 50px;
        background-color: var(--blanco);
        border-radius: 5px;
        color: var(--azul-profundo);
        font-weight: 600;
        border: 1px solid #e0e6ed;
    }
    .stTabs [aria-selected="true"] {
        border-color: var(--verde-lima) !important;
        color: var(--verde-lima) !important;
    }

    /* Barras de Progreso */
    .stProgress > div > div > div > div {
        background-color: var(--verde-lima) !important;
    }

    /* Tarjetas de Información */
    .highlight-card {
        background: var(--fondo-gris);
        padding: 20px;
        border-left: 5px solid var(--verde-lima);
        border-radius: 8px;
        color: var(--azul-profundo);
        margin: 15px 0;
    }
    </style>
    """, unsafe_allow_html=True)

local_css()

# --- 2. ENCABEZADO PERSONALIZADO ---
st.markdown("""
    <div class="custom-header">
        <h1>🛠️ Suite PPK <strong>Universal</strong></h1>
        <p>Procesamiento Geodésico Profesional para Drones DJI & Emlid</p>
    </div>
""", unsafe_allow_html=True)

# --- 3. FUNCIONES NÚCLEO ---
def latlon_to_ecef(lat, lon, alt):
    rad_lat, rad_lon = math.radians(lat), math.radians(lon)
    a, f = 6378137.0, 1 / 298.257223563
    e2 = f * (2 - f)
    N = a / math.sqrt(1 - e2 * math.sin(rad_lat)**2)
    return ((N + alt) * math.cos(rad_lat) * math.cos(rad_lon),
            (N + alt) * math.cos(rad_lat) * math.sin(rad_lon),
            (N * (1 - e2) + alt) * math.sin(rad_lat))

@st.cache_data
def get_geoid_ar16():
    url = "https://cdn.proj.org/ar_ign_GEOIDE-Ar16.tif"
    local = "geode_ar16_ign.tif"
    if not os.path.exists(local):
        r = requests.get(url, timeout=30)
        with open(local, "wb") as f: f.write(r.content)
    return local

# --- 4. CUERPO DE LA APP ---
tabs = st.tabs(["📂 Hatanaka", "🌏 Georreferenciación", "📐 Civil 3D (Ar16)"])

ext_d = ["24d", "25d", "26d", "27d", "d", "24D", "25D", "26D", "27D", "D"]
ext_o = ["o", "obs", "24o", "25o", "26o", "27o", "O", "OBS", "24O", "25O", "26O", "27O"]

with tabs[0]:
    st.markdown('<p class="category-desc">Convierte archivos comprimidos .XXD al estándar RINEX .XXO</p>', unsafe_allow_html=True)
    uploaded_d = st.file_uploader("Cargar archivo comprimido", type=ext_d)
    if uploaded_d and st.button("🚀 Iniciar Conversión"):
        with st.status("Procesando Hatanaka...") as s:
            name = uploaded_d.name.replace(" ", "_")
            with open(name, "wb") as f: f.write(uploaded_d.getbuffer())
            hatanaka.decompress_on_disk(name)
            out = Path(name).with_suffix(Path(name).suffix.replace('d', 'o').replace('D', 'O'))
            if out.exists():
                s.update(label="✅ Listo", state="complete")
                with open(out, "rb") as f:
                    st.download_button("💾 Descargar .O", f, file_name=out.name)

with tabs[1]:
    st.markdown('<div class="highlight-card">Inyecta coordenadas estáticas precisas (.pos) en tu archivo base.</div>', unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    with c1: up_pos = st.file_uploader("Archivo .POS", type=["pos"])
    with c2: up_obs = st.file_uploader("Archivo .O", type=ext_o)
    
    if up_pos and up_obs and st.button("🔗 Vincular Coordenadas"):
        p = st.progress(0)
        txt = st.empty()
        # Lógica de procesamiento (Mantenida de tu código previo)
        txt.text("Calculando ECEF...")
        pos_c = up_pos.getvalue().decode("utf-8").splitlines()
        last = [l for l in pos_c if not l.startswith('%')][-1].split()
        lat, lon, alt = float(last[2]), float(last[3]), float(last[4])
        x, y, z = latlon_to_ecef(lat, lon, alt)
        p.progress(50)
        
        txt.text("Generando archivo final...")
        obs_c = up_obs.getvalue().decode("utf-8").replace("APPROX POSITION XYZ", f"{x:14.4f}{y:14.4f}{z:14.4f}                  APPROX POSITION XYZ")
        p.progress(100)
        st.success(f"X:{x:.3f} Y:{y:.3f} Z:{z:.3f}")
        st.download_button("💾 Descargar Corregido", obs_c, f"CORREGIDO_{up_obs.name}")

with tabs[2]:
    st.markdown('<p class="category-desc">Obtén coordenadas planas POSGAR 07 y cotas ortométricas Ar16.</p>', unsafe_allow_html=True)
    up_rnx = st.file_uploader("RINEX con XYZ", type=ext_o)
    faja = st.selectbox("Faja POSGAR", options=[5343, 5344, 5345, 5346, 5347, 5348, 5349], format_func=lambda x: f"Faja {x-5342}")
    
    if up_rnx and st.button("📐 Calcular PNEZD"):
        with st.status("Cálculo Geodésico...") as s:
            match = re.search(r"([-+0-9.]+)\s+([-+0-9.]+)\s+([-+0-9.]+)\s+APPROX POSITION XYZ", up_rnx.getvalue().decode("utf-8"))
            if match:
                x, y, z = map(float, match.groups())
                t = pyproj.Transformer.from_proj(pyproj.Proj(proj='geocent', ellps='WGS84'), pyproj.Proj(proj='latlong', ellps='WGS84'), always_xy=True)
                ln, lt, h = t.transform(x, y, z)
                with rasterio.open(get_geoid_ar16()) as ds: n = [v[0] for v in ds.sample([(ln, lt)])][0]
                e, n_p = pyproj.Transformer.from_crs(4326, faja, always_xy=True).transform(ln, lt)
                s.update(label="✅ Cálculo Exitoso", state="complete")
                st.info(f"H Orto: {h-n:.4f}m")
                st.download_button("💾 Descargar CSV", f"1,{n_p:.4f},{e:.4f},{h-n:.4f},BASE", "PUNTO.csv")

st.markdown("""
    <div style="text-align:center; padding: 20px; color: #4D4D4D; font-size: 0.8rem;">
        © 2026 | La publicaremos desde google sites.
    </div>
""", unsafe_allow_html=True)
