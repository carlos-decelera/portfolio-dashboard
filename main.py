import streamlit as st
import pandas as pd
import httpx
import asyncio
import plotly.graph_objects as go
import re

# --- CONFIGURACIÓN DE LA PÁGINA ---
st.set_page_config(page_title="Portfolio dashboard", layout="wide")

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
        background-color: #F8F9FA;
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
def mostrar_grafica_notas(notas_dict):
    if not notas_dict:
        st.info("No hay datos históricos.")
        return

    periodos = obtener_periodos_ordenados(notas_dict)
    if not periodos: return

    # Creamos el DataFrame para la gráfica
    df_plot = pd.DataFrame([
        {"label": f"{p[1]}'{p[0][2:]}", "nota": float(p[2][0])} 
        for p in periodos
    ])

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df_plot["label"],
        y=df_plot["nota"],
        mode='lines+markers+text',
        text=df_plot["nota"],
        textposition="top center",
        line=dict(color='#FF4B4B', width=3),
        marker=dict(size=10, color='white', line=dict(width=2, color='#FF4B4B'))
    ))

    fig.update_layout(
        height=250,
        margin=dict(l=0, r=0, t=30, b=0),
        xaxis=dict(type='category', fixedrange=True),
        yaxis=dict(range=[0, 5.5], fixedrange=True, tickvals=[1,2,3,4,5]),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)'
    )
    st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

def historico_a_notas(historico: str):
    if not historico: return {}
    
    notas_dict = {}
    # Limpiamos y separamos por saltos de línea
    lineas = [l.strip() for l in historico.replace('\\n', '\n').split('\n') if l.strip()]

    for linea in lineas:
        # Regex robusta: busca Q(numero), el año de 2 digitos y la nota decimal
        match = re.search(r"(Q[1-4])'(\d{2})\s*-\s*([\d\.]+)", linea)
        if not match: continue
            
        q_label = match.group(1) # "Q1"
        año_full = "20" + match.group(2) # "2026"
        nota_total = match.group(3) # "1.5"

        def extraer_metrica(nombre, texto):
            try:
                # Busca el nombre, salta los dos puntos y coge el número
                pattern = f"{nombre}:\s*([\d\.]+)"
                res = re.search(pattern, texto)
                return res.group(1) if res else "0.0"
            except: return "0.0"

        lista_metrics = [
            extraer_metrica("F&E", linea),
            extraer_metrica("P&E", linea),
            extraer_metrica("M&T", linea),
            extraer_metrica("PMF", linea),
            extraer_metrica("UE", linea),
            extraer_metrica("Narr", linea)
        ]

        if año_full not in notas_dict:
            notas_dict[año_full] = {}
        notas_dict[año_full][q_label] = [nota_total, lista_metrics]

    return notas_dict

def obtener_periodos_ordenados(notas_dict):
    """Devuelve una lista plana ordenada cronológicamente [(año, Q, datos), ...]"""
    lista_plana = []
    for año, trimestres in notas_dict.items():
        for q, datos in trimestres.items():
            lista_plana.append((año, q, datos))
    
    # Ordenamos por año y luego por el número del trimestre
    return sorted(lista_plana, key=lambda x: (x[0], x[1]))

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

    st.markdown("### Datos completos")
    
    def info_row(label, value):
        st.markdown(
            f"""
            <div style="display: flex; justify-content: flex-start; align-items: baseline; margin-bottom: 5px;">
                <span style="font-weight: 600; color: #666; font-size: 0.9rem; min-width: 80px;">{label}:</span>
                <span style="margin-left: 10px; color: #31333F; font-size: 0.95rem;">{value}</span>
            </div>
            """,
            unsafe_allow_html=True
        )

    historico = row.get("historico_categorizacion", None)

    # 1. Inicializamos variables por si no hay histórico
    notas_dict = {}
    año_reciente = "N/A"
    q_reciente = ""
    nota_final_reciente = "N/A"
    lista_notas_recientes = []

    # 2. Solo intentamos extraer si hay datos
    if historico:
        notas_dict = historico_a_notas(historico)
        periodos = obtener_periodos_ordenados(notas_dict)
        
        if periodos:
            # El último de la lista ordenada es el más reciente
            reciente = periodos[-1] 
            año_reciente = reciente[0]
            q_reciente = reciente[1]
            nota_final_reciente = reciente[2][0]
            lista_notas_recientes = reciente[2][1]
        else:
            año_reciente, q_reciente, nota_final_reciente, lista_notas_recientes = "N/A", "", "N/A", []

    # 3. Dibujamos en Streamlit
    col1, col2 = st.columns(2)

    with col1:
        # Mostramos el periodo (ej: 2026 Q1)
        info_row("Última actualización", f"{año_reciente} {q_reciente}")
        info_row("Nota final", nota_final_reciente)

        # Solo iteramos si tenemos notas
        if lista_notas_recientes:
            lista_nombre_notas = ["F&E", "P&E", "M&T", "PMF", "UE", "Narr"]
            for nombre, nota in zip(lista_nombre_notas, lista_notas_recientes):
                info_row(nombre, nota)
        else:
            st.caption("No hay detalles disponibles")

    with col2:
        mostrar_grafica_notas(notas_dict)

# ────────────────────────────────────────────────────────────
# FUNCIÓN PARA COLORES DE STATUS
# ────────────────────────────────────────────────────────────
def get_status_style(status):
    status = str(status).upper()
    styles = {
        "EXITED":     ("#E3F9E5", "#1F7A33"),
        "WRITE-OFF":  ("#FEF3C7", "#92400E"),
        "ACTIVO":     ("#FEE2E2", "#B91C1C"),
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
    st.title("📊 Mi Portfolio Kanban")

    df = get_combined_dataframe()
    if df.empty:
        st.warning("No hay datos disponibles.")
        return

    CATEGORIAS = ["Zombie", "Monitoring", "Good Performer", "Over Performer",  None]
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