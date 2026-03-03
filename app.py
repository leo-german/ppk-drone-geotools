import streamlit as st
import hatanaka
import os
import re
import math
import pyproj
import rasterio
import pandas as pd
import requests
import time
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
        with st.spinner("Descargando Geoide Ar16 oficial (solo la primera vez)..."):
            r = requests.get(url, timeout=30)
            with open(local, "wb") as f: f.write(r.content)
    return local

# --- INTERFAZ DE USUARIO ---
st.title("🛠️ Suite PPK Universal para Drones DJI")
st.markdown("Adaptación profesional para **Streamlit Cloud** con barra de progreso.")

tabs = st.tabs(["📂 Módulo 1: Hatanaka", "🌏 Módulo 3: Georreferenciación", "📐 Civil 3D (Ar16)"])

# Extensiones permitidas (Fix de la versión anterior)
ext_d = ["24d", "25d", "26d", "27d", "d", "24D", "25D", "26D", "27D", "D"]
ext_o = ["o", "obs", "24o", "25o", "26o", "27o", "O", "OBS", "24O", "25O", "26O", "27O"]

# --- MÓDULO 1: HATANAKA ---
with tabs[0]:
    st.header("Conversión .XXD a .XXO")
    uploaded_d = st.file_uploader("Subir archivo RINEX comprimido", type=ext_d)
    
    if uploaded_d:
        clean_name = uploaded_d.name.replace(" ", "_").replace("(", "").replace(")", "")
        with open(clean_name, "wb") as f:
            f.write(uploaded_d.getbuffer())
        
        if st.button("🚀 Convertir a RINEX"):
            with st.status("Ejecutando descompresión Hatanaka...") as status:
                try:
                    hatanaka.decompress_on_disk(clean_name)
                    ext_o_result = Path(clean_name).suffix.replace('d', 'o').replace('D', 'O')
                    out_file = Path(clean_name).with_suffix(ext_o_result)
                    
                    if out_file.exists():
                        status.update(label="✅ Conversión finalizada", state="complete")
                        with open(out_file, "rb") as f:
                            st.download_button("💾 Descargar RINEX .O", f, file_name=out_file.name)
                except Exception as e:
                    status.update(label=f"❌ Error: {e}", state="error")

# --- MÓDULO 3: GEORREFERENCIACIÓN ABSOLUTA ---
with tabs[1]:
    st.header("Inyección de Coordenadas (.pos + .O)")
    c1, c2 = st.columns(2)
    
    with c1: up_pos = st.file_uploader("Archivo .POS (Emlid)", type=["pos"])
    with c2: up_obs = st.file_uploader("Archivo de Observación .O", type=ext_o)
    
    if up_pos and up_obs:
        if st.button("🔗 Vincular Coordenadas"):
            # Contenedores para Feedback
            progreso = st.progress(0)
            texto_estado = st.empty()
            
            try:
                # 1. Leer archivo POS
                texto_estado.text("📖 Leyendo coordenadas del archivo .POS...")
                pos_content = up_pos.getvalue().decode("utf-8")
                lines_pos = [l for l in pos_content.splitlines() if not l.startswith('%') and l.strip()]
                last_data = lines_pos[-1].split()
                lat, lon, alt = float(last_data[2]), float(last_data[3]), float(last_data[4])
                
                # 2. Calcular ECEF
                x, y, z = latlon_to_ecef(lat, lon, alt)
                new_xyz_line = f"{x:14.4f}{y:14.4f}{z:14.4f}                  APPROX POSITION XYZ\n"
                progreso.progress(20)
                
                # 3. Procesar archivo OBS con barra de progreso real
                texto_estado.text("⚙️ Inyectando coordenadas en el archivo de observación...")
                obs_raw = up_obs.getvalue().decode("utf-8").splitlines(keepends=True)
                total_lines = len(obs_raw)
                final_obs_list = []
                
                # Procesamos línea a línea para poder actualizar la barra
                for i, line in enumerate(obs_raw):
                    if "APPROX POSITION XYZ" in line:
                        final_obs_list.append(new_xyz_line)
                    else:
                        final_obs_list.append(line)
                    
                    # Actualizar progreso cada 10% para no afectar el rendimiento
                    if i % max(1, total_lines // 10) == 0:
                        progreso.progress(20 + int((i / total_lines) * 80))
                
                final_obs = "".join(final_obs_list)
                progreso.progress(100)
                texto_estado.success("✅ ¡Procesamiento Exitoso!")
                
                st.info(f"📍 Coordenadas ECEF calculadas:\nX: {x:.4f} | Y: {y:.4f} | Z: {z:.4f}")
                st.download_button("💾 Descargar BASE_FINAL_PPK", final_obs, file_name=f"CORREGIDO_{up_obs.name}")
                
            except Exception as e:
                texto_estado.error(f"❌ Error en el procesamiento: {e}")

# --- MÓDULO CIVIL 3D ---
with tabs[2]:
    st.header("Exportación a Civil 3D (Cota Ortométrica Ar16)")
    up_rnx = st.file_uploader("Subir RINEX con APPROX POSITION XYZ", type=ext_o, key="civil3d_up")
    faja = st.selectbox("Selecciona Faja POSGAR 2007", 
                        options=[5343, 5344, 5345, 5346, 5347, 5348, 5349],
                        format_func=lambda x: f"Faja {x-5342} (EPSG:{x})", index=4)

    if up_rnx:
        if st.button("📐 Calcular PNEZD"):
            with st.status("Realizando cálculos geodésicos...") as status:
                try:
                    content = up_rnx.getvalue().decode("utf-8")
                    match = re.search(r"([-+]?\d*\.\d+|\d+)\s+([-+]?\d*\.\d+|\d+)\s+([-+]?\d*\.\d+|\d+)\s+APPROX POSITION XYZ", content)
                    
                    if match:
                        x, y, z = float(match.group(1)), float(match.group(2)), float(match.group(3))
                        
                        # Geodesia
                        ecef_p = pyproj.Proj(proj='geocent', ellps='WGS84', datum='WGS84')
                        lla_p = pyproj.Proj(proj='latlong', ellps='WGS84', datum='WGS84')
                        trans = pyproj.Transformer.from_proj(ecef_p, lla_p, always_xy=True)
                        lon, lat, h_elip = trans.transform(x, y, z)
                        
                        # Geoide con spinner interno
                        with rasterio.open(get_geoid_ar16()) as ds:
                            for val in ds.sample([(lon, lat)]): n_val = val[0]
                        
                        h_orto = h_elip - n_val
                        proj_p = pyproj.Transformer.from_crs("EPSG:4326", f"EPSG:{faja}", always_xy=True)
                        east, north = proj_p.transform(lon, lat)
                        
                        status.update(label="✅ Cálculos completados", state="complete")
                        
                        st.success(f"Cota Ortométrica (H): {h_orto:.4f} m")
                        csv_data = f"1,{north:.4f},{east:.4f},{h_orto:.4f},BASE_PPK"
                        st.download_button("💾 Descargar CSV para Civil 3D", csv_data, "PUNTO_CIVIL3D.csv")
                    else:
                        status.update(label="❌ No se encontró la etiqueta APPROX POSITION XYZ", state="error")
                except Exception as e:
                    status.update(label=f"❌ Error: {e}", state="error")

st.markdown("---")
st.caption("© 2026 | Todos los derechos reservados.")
