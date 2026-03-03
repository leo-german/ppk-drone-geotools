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
    
    .stProgress > div > div > div > div {
        background-image: linear-gradient(to right, #8CC63F, #B6E37F) !important;
    }
    </style>
    """, unsafe_allow_html=True)

apply_full_styles()

# --- 2. FUNCIONES GEODÉSICAS (SIN CAMBIOS EN LÓGICA, SOLO ROBUSTEZ) ---
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
        with st.spinner("Descargando Geoide Ar16 oficial..."):
            r = requests.get(url, timeout=30)
            with open(local, "wb") as f: f.write(r.content)
    return local

# --- 3. HEADER ---
st.markdown("""
    <div class="dark-header">
        <h1>GEOTOOLS <span>PPK PRO</span></h1>
        <p style="color: #A0AEC0;">Suite Geodésica de Alta Precisión</p>
    </div>
""", unsafe_allow_html=True)

# --- 4. TABS Y MÓDULOS ---
tabs = st.tabs(["⚡ Hatanaka", "🎯 Georreferenciación", "🏗️ Civil 3D"])

ext_d = ["24d", "25d", "26d", "27d", "d", "24D", "25D", "26D", "27D", "D"]
ext_o = ["o", "obs", "24o", "25o", "26o", "27o", "O", "OBS", "24O", "25O", "26O", "27O"]

# MÓDULO 1: HATANAKA
with tabs[0]:
    st.markdown('<div class="module-card"><h3>🚀 Conversión de Archivos Base</h3><p>Convierte RINEX comprimidos (.d) a observación (.o)</p></div>', unsafe_allow_html=True)
    up_d = st.file_uploader("Subir archivo .XXD", type=ext_d, key="u1")
    if up_d and st.button("EJECUTAR CONVERSIÓN", key="b1"):
        with st.status("Procesando...") as s:
            name = up_d.name.replace(" ", "_")
            with open(name, "wb") as f: f.write(up_d.getbuffer())
            hatanaka.decompress_on_disk(name)
            # Detección dinámica de extensión de salida
            suffix = Path(name).suffix
            out_name = name.replace(suffix, suffix.lower().replace('d', 'o'))
            if os.path.exists(out_name):
                s.update(label="✅ Conversión exitosa", state="complete")
                with open(out_name, "rb") as f:
                    st.download_button("💾 DESCARGAR .O", f, file_name=out_name)

# MÓDULO 2: GEORREFERENCIACIÓN
with tabs[1]:
    st.markdown('<div class="module-card"><h3>📍 Inyección de Coordenadas</h3><p>Vincule su archivo .POS con el RINEX de la base.</p></div>', unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    with c1: up_pos = st.file_uploader("Emlid .POS", type=["pos"])
    with c2: up_obs = st.file_uploader("Base .O", type=ext_o)
    
    if up_pos and up_obs and st.button("VINCULAR Y CORREGIR"):
        prog = st.progress(0)
        try:
            # Lectura robusta de coordenadas
            pos_content = up_pos.getvalue().decode("utf-8").splitlines()
            data_lines = [l for l in pos_content if not l.startswith('%') and l.strip()]
            if not data_lines: raise ValueError("Archivo .POS sin datos válidos.")
            
            last = data_lines[-1].split()
            lat, lon, alt = float(last[2]), float(last[3]), float(last[4])
            x, y, z = latlon_to_ecef(lat, lon, alt)
            prog.progress(40)
            
            # Reemplazo en el Header del RINEX
            obs_raw = up_obs.getvalue().decode("utf-8")
            new_xyz = f"{x:14.4f}{y:14.4f}{z:14.4f}                  APPROX POSITION XYZ"
            # Usamos regex para asegurar que reemplazamos la línea correcta incluso si tiene espacios distintos
            final_obs = re.sub(r".*APPROX POSITION XYZ", new_xyz, obs_raw)
            
            prog.progress(100)
            st.success(f"Coordenadas ECEF calculadas: X:{x:.3f} Y:{y:.3f} Z:{z:.3f}")
            st.download_button("💾 DESCARGAR BASE CORREGIDA", final_obs, file_name=f"FIXED_{up_obs.name}")
        except Exception as e:
            st.error(f"Error: {e}")

# MÓDULO 3: CIVIL 3D
with tabs[2]:
    st.markdown('<div class="module-card"><h3>📐 Exportación Civil 3D</h3><p>Cálculo de Cota Ortométrica (Ar16) y Planas (POSGAR).</p></div>', unsafe_allow_html=True)
    up_r = st.file_uploader("RINEX con XYZ", type=ext_o, key="u3")
    faja = st.selectbox("Seleccionar Faja POSGAR", options=[5343, 5344, 5345, 5346, 5347, 5348, 5349], format_func=lambda x: f"Faja {x-5342}")
    
    if up_r and st.button("CALCULAR PNEZD"):
        with st.spinner("Consultando Geoide..."):
            content = up_r.getvalue().decode("utf-8")
            match = re.search(r"([-+0-9.]+)\s+([-+0-9.]+)\s+([-+0-9.]+)\s+APPROX POSITION XYZ", content)
            if match:
                x, y, z = map(float, match.groups())
                # Transformación Geocéntrica a Geográfica
                transformer_lla = pyproj.Transformer.from_crs("EPSG:4978", "EPSG:4326", always_xy=True)
                lon, lat, h_elip = transformer_lla.transform(x, y, z)
                
                # Interpolación Geoide
                with rasterio.open(get_geoid_ar16()) as ds:
                    for val in ds.sample([(lon, lat)]): n_val = val[0]
                
                h_orto = h_elip - n_val
                
                # Proyección Planas
                proj_utm = pyproj.Transformer.from_crs("EPSG:4326", f"EPSG:{faja}", always_xy=True)
                e, n_p = proj_utm.transform(lon, lat)
                
                st.balloons()
                st.info(f"📍 Coordenadas: N:{n_p:.3f} E:{e:.3f} H:{h_orto:.3f}")
                csv = f"1,{n_p:.4f},{e:.4f},{h_orto:.4f},BASE_PPK"
                st.download_button("💾 DESCARGAR CSV PNEZD", csv, "PUNTO_BASE.csv")
            else:
                st.error("No se encontró la etiqueta APPROX POSITION XYZ en el archivo.")

st.markdown('<div style="text-align:center; padding: 20px; opacity: 0.5; font-size: 0.7rem;">© 2026 | Publicado desde Google Sites</div>', unsafe_allow_html=True)
