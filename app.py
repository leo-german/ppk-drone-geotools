import streamlit as st
import hatanaka
import os
import re
import math
import pyproj
import rasterio
import pandas as pd
import requests
from pathlib import Path

# --- CONFIGURACIÓN DE LA PÁGINA ---
st.set_page_config(page_title="PPK Drone Geotools", page_icon="🛰️", layout="wide")

# --- FUNCIONES NÚCLEO ---
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

# --- INTERFAZ DE USUARIO ---
st.title("🛠️ Suite PPK Universal para Drones DJI")
st.markdown("Adaptación profesional para **Streamlit Cloud**.")

tabs = st.tabs(["📂 Módulo 1: Descompresión RINEX", "🌏 Módulo 2: Georreferenciación", "📐 Módulo 3: Civil 3D (Ar16)"])

# --- MÓDULO 1: HATANAKA ---
with tabs[0]:
    st.header("Conversión .XXD a .XXO")
    # LISTA AMPLIADA PARA COMPRIMIDOS
    ext_d = ["24d", "25d", "26d", "27d", "d", "24D", "25D", "26D", "27D", "D"]
    uploaded_d = st.file_uploader("Subir archivo RINEX comprimido", type=ext_d)
    
    if uploaded_d:
        clean_name = uploaded_d.name.replace(" ", "_").replace("(", "").replace(")", "")
        with open(clean_name, "wb") as f:
            f.write(uploaded_d.getbuffer())
        
        if st.button("🚀 Convertir a RINEX"):
            try:
                hatanaka.decompress_on_disk(clean_name)
                ext_o = Path(clean_name).suffix.replace('d', 'o').replace('D', 'O')
                out_file = Path(clean_name).with_suffix(ext_o)
                
                if out_file.exists():
                    with open(out_file, "rb") as f:
                        st.download_button("💾 Descargar RINEX .O", f, file_name=out_file.name)
                    st.success(f"Archivo {out_file.name} listo.")
            except Exception as e:
                st.error(f"Error en la conversión: {e}")

# --- MÓDULO 2: GEORREFERENCIACIÓN ABSOLUTA ---
with tabs[1]:
    st.header("Inyección de Coordenadas (.pos + .O)")
    c1, c2 = st.columns(2)
    # LISTA AMPLIADA PARA OBSERVACIONES
    ext_o = ["o", "obs", "24o", "25o", "26o", "27o", "O", "OBS", "24O", "25O", "26O", "27O"]
    
    with c1: 
        up_pos = st.file_uploader("Archivo .POS (Emlid)", type=["pos"])
    with c2: 
        up_obs = st.file_uploader("Archivo de Observación .O", type=ext_o)
    
    if up_pos and up_obs:
        if st.button("🔗 Vincular Coordenadas"):
            try:
                pos_content = up_pos.getvalue().decode("utf-8")
                lines = [l for l in pos_content.splitlines() if not l.startswith('%') and l.strip()]
                last_data = lines[-1].split()
                lat, lon, alt = float(last_data[2]), float(last_data[3]), float(last_data[4])
                
                x, y, z = latlon_to_ecef(lat, lon, alt)
                new_xyz_line = f"{x:14.4f}{y:14.4f}{z:14.4f}                  APPROX POSITION XYZ\n"
                
                obs_content = up_obs.getvalue().decode("utf-8")
                final_obs = ""
                for line in obs_content.splitlines(keepends=True):
                    if "APPROX POSITION XYZ" in line:
                        final_obs += new_xyz_line
                    else:
                        final_obs += line
                
                st.download_button("💾 Descargar BASE_FINAL_PPK", final_obs, file_name=f"CORREGIDO_{up_obs.name}")
                st.info(f"Coordenadas ECEF inyectadas: X:{x:.4f} Y:{y:.4f} Z:{z:.4f}")
            except Exception as e:
                st.error(f"Error al procesar: {e}")

# --- MÓDULO 3 CIVIL 3D ---
with tabs[2]:
    st.header("Exportación a Civil 3D (Cota Ortométrica Ar16)")
    # LISTA AMPLIADA PARA RINEX FINAL
    up_rnx = st.file_uploader("Subir RINEX con APPROX POSITION XYZ", type=ext_o)
    faja = st.selectbox("Selecciona Faja POSGAR 2007", 
                        options=[5343, 5344, 5345, 5346, 5347, 5348, 5349],
                        format_func=lambda x: f"Faja {x-5342} (EPSG:{x})", index=4)

    if up_rnx:
        if st.button("📐 Calcular PNEZD"):
            try:
                content = up_rnx.getvalue().decode("utf-8")
                match = re.search(r"([-+]?\d*\.\d+|\d+)\s+([-+]?\d*\.\d+|\d+)\s+([-+]?\d*\.\d+|\d+)\s+APPROX POSITION XYZ", content)
                
                if match:
                    x, y, z = float(match.group(1)), float(match.group(2)), float(match.group(3))
                    
                    ecef_p = pyproj.Proj(proj='geocent', ellps='WGS84', datum='WGS84')
                    lla_p = pyproj.Proj(proj='latlong', ellps='WGS84', datum='WGS84')
                    trans = pyproj.Transformer.from_proj(ecef_p, lla_p, always_xy=True)
                    lon, lat, h_elip = trans.transform(x, y, z)
                    
                    with rasterio.open(get_geoid_ar16()) as ds:
                        for val in ds.sample([(lon, lat)]): n_val = val[0]
                    
                    h_orto = h_elip - n_val
                    
                    proj_p = pyproj.Transformer.from_crs("EPSG:4326", f"EPSG:{faja}", always_xy=True)
                    east, north = proj_p.transform(lon, lat)
                    
                    st.success(f"Cota Ortométrica calculada: {h_orto:.4f} m (N Ar16: {n_val:.4f}m)")
                    
                    csv_data = f"1,{north:.4f},{east:.4f},{h_orto:.4f},BASE_PPK"
                    st.download_button("💾 Descargar CSV para Civil 3D", csv_data, "PUNTO_CIVIL3D.csv")
                else:
                    st.error("No se encontró 'APPROX POSITION XYZ' en el encabezado.")
            except Exception as e:
                st.error(f"Error en el cálculo geodésico: {e}")

st.markdown("---")
st.caption("© 2026 | La publicaremos desde google sites.")
