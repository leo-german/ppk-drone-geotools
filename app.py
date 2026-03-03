import streamlit as st
import hatanaka
import os
import re
import math
import pyproj
import rasterio
import requests
import time
from pathlib import Path

# --- 1. CONFIGURACIÓN Y ESTILO DARK ---
st.set_page_config(page_title="PPK Drone Geotools | Dark", page_icon="🛰️", layout="wide")

def local_css():
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@300;400;600;700&display=swap');

    /* Paleta Dark Mode */
    :root {
        --fondo-oscuro: #0E1117;
        --azul-card: #142032;
        --verde-lima: #8CC63F;
        --texto-blanco: #FFFFFF;
        --texto-gris: #A0AEC0;
        --borde: #1E293B;
    }

    .stApp {
        background-color: var(--fondo-oscuro);
        font-family: 'Montserrat', sans-serif;
        color: var(--texto-blanco);
    }

    /* Header Estilo Neon */
    .dark-header {
        background-color: var(--azul-card);
        padding: 40px 20px;
        text-align: center;
        border-bottom: 4px solid var(--verde-lima);
        box-shadow: 0 4px 20px rgba(140, 198, 63, 0.2);
        margin-bottom: 40px;
        border-radius: 0 0 15px 15px;
    }
    .dark-header h1 {
        color: var(--texto-blanco) !important;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 2px;
        margin-bottom: 10px;
    }
    .dark-header span { color: var(--verde-lima); }

    /* Inputs y File Uploader */
    .stFileUploader section {
        background-color: var(--azul-card) !important;
        border: 1px dashed var(--verde-lima) !important;
        color: var(--texto-blanco) !important;
    }

    /* Botones Estilo "Glow" */
    .stButton>button {
        background-color: var(--verde-lima) !important;
        color: #000000 !important;
        font-weight: 700 !important;
        border-radius: 8px !important;
        border: none !important;
        width: 100%;
        padding: 12px !important;
        transition: all 0.3s ease;
        box-shadow: 0 0 10px rgba(140, 198, 63, 0.3);
    }
    .stButton>button:hover {
        transform: translateY(-2px);
        box-shadow: 0 0 20px rgba(140, 198, 63, 0.6);
    }

    /* Tabs Personalizados */
    .stTabs [data-baseweb="tab-list"] {
        background-color: transparent;
        gap: 20px;
    }
    .stTabs [data-baseweb="tab"] {
        background-color: var(--azul-card);
        border: 1px solid var(--borde);
        color: var(--texto-gris);
        border-radius: 8px 8px 0 0;
        padding: 10px 30px;
    }
    .stTabs [aria-selected="true"] {
        border-bottom: 3px solid var(--verde-lima) !important;
        color: var(--verde-lima) !important;
        background-color: rgba(140, 198, 63, 0.05);
    }

    /* Tarjetas Modulares */
    .module-card {
        background-color: var(--azul-card);
        padding: 25px;
        border-radius: 12px;
        border: 1px solid var(--borde);
        margin-bottom: 20px;
    }

    /* Barra de Progreso */
    .stProgress > div > div > div > div {
        background-image: linear-gradient(to right, #8CC63F, #B6E37F) !important;
    }
    </style>
    """, unsafe_allow_html=True)

local_css()

# --- 2. HEADER ---
st.markdown("""
    <div class="dark-header">
        <h1>GEOTOOLS <span>DARK EDITION</span></h1>
        <p style="color: #A0AEC0;">Suite Geodésica Profesional DJI & EMLID</p>
    </div>
""", unsafe_allow_html=True)

# --- 3. FUNCIONES ---
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

# --- 4. TABS ---
tabs = st.tabs(["⚡ Hatanaka", "🎯 Georreferenciación", "🏗️ Civil 3D Ar16"])

ext_d = ["24d", "25d", "26d", "27d", "d", "24D", "25D", "26D", "27D", "D"]
ext_o = ["o", "obs", "24o", "25o", "26o", "27o", "O", "OBS", "24O", "25O", "26O", "27O"]

with tabs[0]:
    st.markdown('<div class="module-card"><h3>🚀 Conversión de Archivos Base</h3><p style="color: #A0AEC0;">Descomprime archivos RINEX Compact (.d) a formato estándar (.o)</p></div>', unsafe_allow_html=True)
    up_d = st.file_uploader("Subir archivo .XXD", type=ext_d)
    if up_d and st.button("EJECUTAR CONVERSIÓN"):
        with st.status("⚡ Procesando algoritmo Hatanaka...") as s:
            name = up_d.name.replace(" ", "_")
            with open(name, "wb") as f: f.write(up_d.getbuffer())
            hatanaka.decompress_on_disk(name)
            out = Path(name).with_suffix(Path(name).suffix.lower().replace('d', 'o'))
            if out.exists():
                s.update(label="✅ Archivo listo para descarga", state="complete")
                with open(out, "rb") as f:
                    st.download_button("💾 DESCARGAR RINEX (.O)", f, file_name=out.name)

with tabs[1]:
    st.markdown('<div class="module-card"><h3>📍 Inyección de Coordenadas Precisas</h3><p style="color: #A0AEC0;">Vincula archivos .POS de Emlid con tus archivos de observación base.</p></div>', unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    with c1: up_pos = st.file_uploader("Archivo Emlid .POS", type=["pos"])
    with c2: up_obs = st.file_uploader("Observación Base .O", type=ext_o)
    
    if up_pos and up_obs and st.button("VINCULAR Y CORREGIR"):
        p = st.progress(0)
        st.write("🛠️ Procesando datos...")
        # Lógica
        pos_lines = up_pos.getvalue().decode("utf-8").splitlines()
        last = [l for l in pos_lines if not l.startswith('%')][-1].split()
        lat, lon, alt = float(last[2]), float(last[3]), float(last[4])
        x, y, z = latlon_to_ecef(lat, lon, alt)
        p.progress(40)
        
        obs_c = up_obs.getvalue().decode("utf-8")
        final = obs_c.replace("APPROX POSITION XYZ", f"{x:14.4f}{y:14.4f}{z:14.4f}                  APPROX POSITION XYZ")
        p.progress(100)
        st.success(f"Coordenadas ECEF inyectadas correctamente")
        st.download_button("💾 DESCARGAR BASE FINAL", final, file_name=f"FINAL_{up_obs.name}")

with tabs[2]:
    st.markdown('<div class="module-card"><h3>📐 Exportación a Ingeniería</h3><p style="color: #A0AEC0;">Genera puntos PNEZD con cota ortométrica Ar16 para Civil 3D.</p></div>', unsafe_allow_html=True)
    up_r = st.file_uploader("RINEX con XYZ Corregido", type=ext_o)
    faja = st.selectbox("Sistema de Coordenadas (Faja POSGAR)", options=[5343, 5344, 5345, 5346, 5347, 5348, 5349], format_func=lambda x: f"Faja {x-5342} (EPSG:{x})")
    
    if up_r and st.button("CALCULAR PNEZD"):
        with st.spinner("🌍 Consultando Geoide Ar16..."):
            match = re.search(r"([-+0-9.]+)\s+([-+0-9.]+)\s+([-+0-9.]+)\s+APPROX POSITION XYZ", up_r.getvalue().decode("utf-8"))
            if match:
                x, y, z = map(float, match.groups())
                t = pyproj.Transformer.from_proj(pyproj.Proj(proj='geocent', ellps='WGS84'), pyproj.Proj(proj='latlong', ellps='WGS84'), always_xy=True)
                ln, lt, h = t.transform(x, y, z)
                with rasterio.open(get_geoid_ar16()) as ds: n = [v[0] for v in ds.sample([(ln, lt)])][0]
                e, n_p = pyproj.Transformer.from_crs(4326, faja, always_xy=True).transform(ln, lt)
                
                st.balloons()
                st.info(f"Cota Ortométrica Calculada: {h-n:.4f} m")
                st.download_button("💾 DESCARGAR CSV PARA CIVIL 3D", f"1,{n_p:.4f},{e:.4f},{h-n:.4f},BASE_PPK", "CIVIL3D_BASE.csv")

st.markdown("""
    <div style="text-align:center; padding: 40px; color: #4D4D4D; font-size: 0.75rem; letter-spacing: 1px;">
        PROCESAMIENTO PPK DJI | 2026 | PUBLICADO EN GOOGLE SITES
    </div>
""", unsafe_allow_html=True)
