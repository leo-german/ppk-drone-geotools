import streamlit as st
import hatanaka
import os
import re
import math
import pyproj
import rasterio
import requests
from pathlib import Path

# --- 1. CONFIGURACIÓN DE PÁGINA Y ESTILO TOTAL ---
st.set_page_config(page_title="PPK Drone Geotools | Pro Edition", page_icon="🛰️", layout="wide")

def apply_full_styles():
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@300;400;600;700&display=swap');

    /* Reset global de tipografía */
    html, body, [class*="st-"], .stApp, button, input, p, span, div, h1, h2, h3, label {
        font-family: 'Montserrat', sans-serif !important;
    }

    :root {
        --fondo-oscuro: #0E1117;
        --azul-card: #142032;
        --verde-lima: #8CC63F;
        --texto-blanco: #FFFFFF;
        --borde: #1E293B;
    }

    .stApp { background-color: var(--fondo-oscuro); color: var(--texto-blanco); }

    /* Forzar visibilidad de la barra de progreso */
    .stProgress [role="progressbar"] > div > div {
        background-color: var(--verde-lima) !important;
    }
    
    .dark-header {
        background-color: var(--azul-card);
        padding: 40px 20px;
        text-align: center;
        border-bottom: 4px solid var(--verde-lima);
        box-shadow: 0 4px 20px rgba(140, 198, 63, 0.2);
        margin-bottom: 40px;
        border-radius: 0 0 15px 15px;
    }
    
    .module-card {
        background-color: var(--azul-card);
        padding: 25px;
        border-radius: 12px;
        border: 1px solid var(--borde);
        margin-bottom: 20px;
    }

    .stButton>button {
        background-color: var(--verde-lima) !important;
        color: #000000 !important;
        font-weight: 700 !important;
        border-radius: 8px !important;
        width: 100%;
        transition: all 0.3s ease;
    }
    </style>
    """, unsafe_allow_html=True)

apply_full_styles()

# --- 2. FUNCIONES GEODÉSICAS ---
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

# --- 3. HEADER ---
st.markdown("""
    <div class="dark-header">
        <h1>GEOTOOLS <span>PPK PRO</span></h1>
        <p style="color: #A0AEC0;">Suite Geodésica | 2026 Edition</p>
    </div>
""", unsafe_allow_html=True)

tabs = st.tabs(["⚡ Hatanaka", "🎯 Georreferenciación", "🏗️ Civil 3D"])

ext_d = ["24d", "25d", "26d", "27d", "d", "D"]
ext_o = ["o", "obs", "24o", "25o", "26o", "27o", "O", "OBS"]

# MÓDULO 1: HATANAKA (CORREGIDO)
with tabs[0]:
    st.markdown('<div class="module-card"><h3>🚀 Conversión Hatanaka</h3><p>Descompresión de archivos RINEX Compact en memoria.</p></div>', unsafe_allow_html=True)
    up_d = st.file_uploader("Subir archivo .XXD", type=ext_d)
    if up_d and st.button("EJECUTAR CONVERSIÓN"):
        try:
            # Leemos el contenido comprimido
            compressed_data = up_d.getvalue()
            # Descomprimimos directamente el buffer
            decompressed_data = hatanaka.decompress(compressed_data)
            
            # Generamos el nombre de salida (.o)
            out_name = up_d.name.lower().replace('d', 'o')
            
            st.success("✅ Conversión completada con éxito")
            st.download_button("💾 DESCARGAR RINEX (.O)", decompressed_data, file_name=out_name)
        except Exception as e:
            st.error(f"Error en descompresión: {e}")

# MÓDULO 2: GEORREFERENCIACIÓN (CON BARRA CORREGIDA)
with tabs[1]:
    st.markdown('<div class="module-card"><h3>📍 Inyección de Coordenadas</h3><p>Vincule su archivo .POS con el RINEX de la base.</p></div>', unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    with c1: up_pos = st.file_uploader("Emlid .POS", type=["pos"])
    with c2: up_obs = st.file_uploader("Base .O", type=ext_o)
    
    if up_pos and up_obs and st.button("VINCULAR Y CORREGIR"):
        prog_bar = st.progress(0)
        try:
            pos_content = up_pos.getvalue().decode("utf-8").splitlines()
            data_lines = [l for l in pos_content if not l.startswith('%') and l.strip()]
            last = data_lines[-1].split()
            lat, lon, alt = float(last[2]), float(last[3]), float(last[4])
            x, y, z = latlon_to_ecef(lat, lon, alt)
            
            prog_bar.progress(50) # Ahora será visible en verde lima
            
            obs_raw = up_obs.getvalue().decode("utf-8")
            new_xyz = f"{x:14.4f}{y:14.4f}{z:14.4f}                  APPROX POSITION XYZ"
            final_obs = re.sub(r".*APPROX POSITION XYZ", new_xyz, obs_raw)
            
            prog_bar.progress(100)
            st.success("Coordenadas inyectadas.")
            st.download_button("💾 DESCARGAR BASE FINAL", final_obs, file_name=f"FIXED_{up_obs.name}")
        except Exception as e:
            st.error(f"Error: {e}")

# MÓDULO 3: CIVIL 3D
with tabs[2]:
    st.markdown('<div class="module-card"><h3>📐 Exportación Civil 3D</h3><p>Cálculo de Cota Ar16 y Proyección POSGAR.</p></div>', unsafe_allow_html=True)
    up_r = st.file_uploader("RINEX corregido", type=ext_o)
    faja = st.selectbox("Faja POSGAR", options=[5343, 5344, 5345, 5346, 5347, 5348, 5349], format_func=lambda x: f"Faja {x-5342}")
    
    if up_r and st.button("GENERAR PNEZD"):
        with st.spinner("Procesando geoide..."):
            content = up_r.getvalue().decode("utf-8")
            match = re.search(r"([-+0-9.]+)\s+([-+0-9.]+)\s+([-+0-9.]+)\s+APPROX POSITION XYZ", content)
            if match:
                x, y, z = map(float, match.groups())
                t_lla = pyproj.Transformer.from_crs("EPSG:4978", "EPSG:4326", always_xy=True)
                ln, lt, h_e = t_lla.transform(x, y, z)
                
                with rasterio.open(get_geoid_ar16()) as ds:
                    for v in ds.sample([(ln, lt)]): n_v = v[0]
                
                h_o = h_e - n_v
                t_p = pyproj.Transformer.from_crs("EPSG:4326", f"EPSG:{faja}", always_xy=True)
                e, n_p = t_p.transform(ln, lt)
                
                st.info(f"H. Ortométrica: {h_o:.3f} m")
                csv = f"1,{n_p:.4f},{e:.4f},{h_o:.4f},BASE_PPK"
                st.download_button("💾 DESCARGAR CSV", csv, "CIVIL_BASE.csv")

st.markdown('<div style="text-align:center; padding: 20px; opacity: 0.5; font-size: 0.7rem;">© 2026 | Google Sites Integration</div>', unsafe_allow_html=True)
