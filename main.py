import streamlit as st
import pandas as pd
import httpx
import asyncio
import plotly.graph_objects as go
import re

# --- CONFIGURACIÓN DE LA PÁGINA ---
st.set_page_config(page_title="Portfolio Kanban", layout="wide", page_icon="https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcTb_FaT4TLTs0RVC0zxBnYT2pUjrN3JJKIY6Q&s")

# Configuración de IDs (Asegúrate de tener ATTIO_API_KEY en st.secrets)
ATTIO_API_KEY = st.secrets["ATTIO_API_KEY"]
COMPANIES_ID = "74c77546-6a6f-4aab-9a19-536d8cfed976"
PORTFOLIO_ID = "ff9d54b8-b5cb-4441-97ea-efd4a6d2a5a7"
BASE_URL = "https://api.attio.com/v2"

HEADERS = {
    "Authorization": f"Bearer {ATTIO_API_KEY}",
    "Content-Type": "application/json",
}

# ────────────────────────────────────────────────────────────
# ESTILOS CSS
# ────────────────────────────────────────────────────────────
st.markdown(
    """
    <style>
    .st-emotion-cache-o29vc0 {
        background-color: #FFFFFF;
        padding: 1rem;
        border-radius: 12px;
        border: 2px solid #EDEDED;
        margin-bottom: 0.1rem;
    }
    </style>
    """,
    unsafe_allow_html=True
)

st.markdown("""
<style>
    /* Fondo general uniforme — gris claro */
    .stApp {
        background-color: #FFFFFF;
    }

    /* Eliminar cualquier fondo extra en bloques verticales */
    [data-testid="stVerticalBlock"] > div:has(div.column-header) {
        background-color: transparent;
        padding: 0;
        border-radius: 0;
    }

    /* Columnas del Kanban — blanco roto */
    [data-testid="column"] {
        background-color: #F8F9FA !important;
        padding: 12px !important;
        border-radius: 10px !important;
        margin: 0 5px !important;
        border: 1px solid #e5e2dd !important;
        box-shadow: 0 1px 4px rgba(0,0,0,0.07) !important;
    }

    /* Títulos de las columnas */
    .column-header {
        font-family: 'Inter', sans-serif;
        color: #444;
        font-weight: bold;
        text-align: center;
        padding-bottom: 10px;
    }

    /* Tarjetas — wrapper exterior */
    [data-testid="stVerticalBlockBorderWrapper"] {
        background-color: #f5f3f0 !important;
        border: 1px solid #dedad4 !important;
        border-radius: 8px !important;
        box-shadow: 0 1px 3px rgba(0,0,0,0.08) !important;
    }

    /* Todo lo que hay DENTRO de una tarjeta hereda el blanco roto */
    [data-testid="stVerticalBlockBorderWrapper"] * {
        background-color: inherit !important;
    }

    /* Excepcion: badges de status y botones mantienen su propio color */
    [data-testid="stVerticalBlockBorderWrapper"] span,
    [data-testid="stVerticalBlockBorderWrapper"] button,
    [data-testid="stVerticalBlockBorderWrapper"] img {
        background-color: unset !important;
    }

    /* Botones */
    div.stButton > button {
        width: 100%;
        height: 25px;
        font-size: 12px !important;
        padding: 0px !important;
        margin-top: 8px !important;
    }
</style>
""", unsafe_allow_html=True)

# ────────────────────────────────────────────────────────────
# FUNCIONES DE DATOS
# ────────────────────────────────────────────────────────────

def extract_value(attr_list):
    if not attr_list: return None
    extracted = []
    for item in attr_list:
        attr_type = item.get("attribute_type", "")
        val = None
        if attr_type == "status": val = item.get("status", {}).get("title")
        elif attr_type == "select": val = item.get("option", {}).get("title")
        elif attr_type == "domain": val = item.get("domain")
        elif attr_type == "location": val = item.get("country_code")
        elif attr_type in ("text", "number", "date", "currency"):
            val = item.get("value") or item.get("currency_value")
        if val is not None: extracted.append(str(val))
    return "\n".join(extracted) if extracted else None

async def obtener_notas_attio(record_id: str):

    url = f"{BASE_URL}/notes"
    
    params = {
        "parent_record_id": record_id,
        "parent_object": "companies",
        "limit": 50
    }

    try:
        async with httpx.AsyncClient() as client:

            response = await client.get(url, headers=HEADERS, params=params)
            
            response.raise_for_status()
            
            data = response.json()
            return data.get("data", [])
            
    except httpx.HTTPStatusError as e:
        st.error(f"Error de API Attio: {e.response.status_code}")
        return []
    except Exception as e:
        st.error(f"Error inesperado: {e}")
        return []

async def fetch_data(client, url, payload=None):
    all_data, limit, offset = [], 100, 0
    while True:
        current_payload = {**(payload or {}), "limit": limit, "offset": offset}
        response = await client.post(url, headers=HEADERS, json=current_payload)
        response.raise_for_status()
        data = response.json().get("data", [])
        all_data.extend(data)
        if len(data) < limit: break
        offset += limit
    return all_data

def transform_attio_to_df(attio_data):
    rows = []
    for record in attio_data:
        record_id = record.get("id", {}).get("record_id") or record.get("parent_record_id")
        row = {"record_id": str(record_id)}
        values_source = record.get("entry_values", {}) or record.get("values", {})
        for attr_name, attr_list in values_source.items():
            row[attr_name] = extract_value(attr_list)
        rows.append(row)
    return pd.DataFrame(rows)

@st.cache_data(ttl=600)
def get_combined_dataframe():
    async def run_fetches():
        async with httpx.AsyncClient() as client:
            raw_entries = await fetch_data(client, f"{BASE_URL}/lists/{PORTFOLIO_ID}/entries/query")
            parent_ids = list({e["parent_record_id"] for e in raw_entries if e.get("parent_record_id")})
            all_records = []
            for i in range(0, len(parent_ids), 100):
                chunk = parent_ids[i:i + 100]
                records = await fetch_data(client, f"{BASE_URL}/objects/{COMPANIES_ID}/records/query",
                                         payload={"filter": {"record_id": {"$in": chunk}}})
                all_records.extend(records)
            return raw_entries, all_records
    try:
        raw_entries, raw_records = asyncio.run(run_fetches())
        df_entries = transform_attio_to_df(raw_entries)
        df_records = transform_attio_to_df(raw_records)
        df_res = df_entries.merge(df_records, on="record_id", how="left", suffixes=("_list", "_company"))
        return df_res
    except Exception as e:
        st.error(f"Error cargando datos: {e}")
        return pd.DataFrame()

# ────────────────────────────────────────────────────────────
# DIALOG / POPUP
# ────────────────────────────────────────────────────────────
@st.dialog("Detalle de la Compañía", width="large")
def show_company_detail(row):
    c1, c2 = st.columns([1, 4])
    logo = row.get("logo_url") or row.get("logo")
    with c1:
        if logo: st.image(logo, width=100)
    with c2:
        st.subheader(row.get("name", "Sin nombre"))
        st.caption(f"ID: {row.get('record_id')}")

    st.markdown("")

    descripcion = str(row.get("description", "N/A")).split(".")[0].strip() + "."
    st.markdown(descripcion)

    st.divider()

    estilo_dato_metrica = """
        <div style="line-height: 1.2;">
            <p style="color: gray; font-size: 0.85rem; margin-bottom: 2px;">{titulo}</p>
            <p style="font-size: 1.1rem; font-weight: 500; color #31333F;">{valor}</p>
        </div>
    """
    col_a, col_b, col_c = st.columns(3)

    with col_a:
        status_raw = str(row.get("categorizacion", "N/A"))
        status_formateado = status_raw.capitalize()
        st.markdown(estilo_dato_metrica.format(titulo="Categoría", valor=status_formateado), unsafe_allow_html=True)

    with col_b:
        stage = row.get("stage") or "N/A"
        st.markdown(estilo_dato_metrica.format(titulo="Stage", valor=stage), unsafe_allow_html=True)

    with col_c:
        year = row.get("investment_year") or "N/A"
        st.markdown(estilo_dato_metrica.format(titulo="Año de inversión", valor=year), unsafe_allow_html=True)
    
    st.divider()

    st.markdown("### Notas de llamadas")

    notas = asyncio.run(obtener_notas_attio(row["record_id"]))

    if not notas:
        st.info("No hay notas registradas para esta compañía")
    else:
        with st.container(height=400):
            for nota in notas:
                titulo = nota.get("title", "Nota sin título").strip()
                texto_nota = nota.get("content_markdown", "Nota sin texto")
                fecha_iso = nota.get("created_at")
                fecha_formateada = pd.to_datetime(fecha_iso).strftime("%d %b %Y, %H:%M")

                with st.chat_message("note"):
                    st.markdown(f"#### {titulo}")
                    st.caption(fecha_formateada)
                    st.markdown(texto_nota)
                    st.divider()

# ────────────────────────────────────────────────────────────
# FUNCIÓN PARA COLORES DE STATUS
# ────────────────────────────────────────────────────────────
def get_status_style(status):
    status = str(status).upper()
    styles = {
        "EXITED":     ("#E3F9E5", "#1F7A33"),
        "ACTIVO":  ("#FEF3C7", "#92400E"),
        "WRITE-OFF":     ("#FEE2E2", "#B91C1C"),
    }
    bg, fg = styles.get(status, ("#F3F4F6", "#374151"))
    return f"""
        <span style="
            background-color: {bg};
            color: {fg};
            padding: 2px 8px;
            border-radius: 12px;
            font-size: 10px;
            font-weight: bold;
            display: inline-block;
            margin-top: 4px;
        ">
            {status}
        </span>
    """

# ────────────────────────────────────────────────────────────
# INTERFAZ KANBAN
# ────────────────────────────────────────────────────────────
def main():
    #Configuracion del logo y titulo
    logo_url = "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcTb_FaT4TLTs0RVC0zxBnYT2pUjrN3JJKIY6Q&s"
    titulo_texto = "Portfolio Decelera Ventures I"

    st.markdown(
        f"""
        <div style="display: flex; align-items: center; margin-bottom: 20px;">
            <img src="{logo_url}" style="width: 70px; height: 70px; margin-right: 15px;">
            <h1 style="margin: 0; font-family: 'Inter', sans-serif; color: #31333F; font-size: 2.2rem;">
                {titulo_texto}
            </h1>
        </div>
    """,
    unsafe_allow_html=True
    )
    st.divider()

    df = get_combined_dataframe()
    if df.empty:
        st.warning("No hay datos disponibles.")
        return

    CATEGORIAS = ["Over Performer", "Good Performer",  "Monitoring", "Zombie", "Write-off", "Exited"]
    cols = st.columns(len(CATEGORIAS))

    for i, cat in enumerate(CATEGORIAS):
        with cols[i]:
            subset = df[df["categorizacion"] == cat] if cat else df[df["categorizacion"].isna() | (df["categorizacion"] == "")]

            titulo_text = (cat if cat else "SIN CATEGORÍA").upper()
            st.markdown(f'<div class="column-header">{titulo_text} ({len(subset)})</div>', unsafe_allow_html=True)

            for _, row in subset.iterrows():
                logo = row.get("logo_url") or row.get("logo") or "https://cdn-icons-png.flaticon.com/512/3616/3616930.png"

                with st.container(border=True):
                    c_logo, c_info, c_button = st.columns([0.6, 2, 0.6])

                    with c_logo:
                        st.image(logo, width=35)

                    with c_info:
                        st.markdown(f"**{row['name']}**")
                        st.markdown(get_status_style(row.get('status', 'N/A')), unsafe_allow_html=True)

                    with c_button:
                        if st.button("➕", key=f"btn_{row['record_id']}"):
                            show_company_detail(row.to_dict())

if __name__ == "__main__":
    main()