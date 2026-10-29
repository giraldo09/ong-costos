"""Tablero de costos por centro (ONG) - lee la vista vw_costos_powerbi de Neon con un rol de solo lectura."""
import os

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

st.set_page_config(page_title="Costos por centro", page_icon="📊", layout="wide")

AZUL, VERDE, ROJO, GRIS = "#1F4E79", "#2E8B57", "#C0392B", "#7F8C8D"
MESES = ["", "Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
VALORES = ["ingresos_operacionales", "ingresos_no_operacionales", "gastos_operacionales",
           "gastos_no_operacionales", "costos", "deficit_excedente"]
SERIES = {"Ingresos": "ingresos", "Gastos y costos": "gastos_costos", "Excedente / (Déficit)": "deficit_excedente"}

st.markdown(
    """<style>
div[data-testid="stMetric"] {background:rgba(128,128,128,0.08); border:1px solid rgba(128,128,128,0.25);
  border-radius:10px; padding:14px 16px;}
h1, h2, h3 {letter-spacing:-0.01em;}
</style>""",
    unsafe_allow_html=True,
)


def _url():
    try:
        u = st.secrets["DATABASE_URL_LECTOR"]
    except Exception:
        load_dotenv(".env.lector")
        u = os.getenv("DATABASE_URL_LECTOR")
    if not u:
        st.error("Falta DATABASE_URL_LECTOR (en .env.lector o en los secretos de Streamlit).")
        st.stop()
    return "postgresql+psycopg2://" + u.strip().strip("'\"").split("://", 1)[1]


@st.cache_resource
def _engine():
    return create_engine(_url(), pool_pre_ping=True)


@st.cache_data(ttl=300, show_spinner="Consultando la base de datos...")
def cargar():
    df = pd.read_sql(text("select * from vw_costos_powerbi"), _engine())
    df["fecha"] = pd.to_datetime(df["fecha"])
    for c in VALORES:
        df[c] = df[c].astype(float)
    df["ingresos"] = df.ingresos_operacionales + df.ingresos_no_operacionales
    df["gastos_costos"] = df.gastos_operacionales + df.gastos_no_operacionales + df.costos
    return df


def money(v, signo=False):
    s = "-" if v < 0 else ("+" if signo and v > 0 else "")
    a = abs(v)
    if a >= 1e6:
        return f"{s}${a / 1e6:,.0f} M" if a >= 1e8 else f"{s}${a / 1e6:,.1f} M"
    return f"{s}${a:,.0f}"


def etiqueta_mes(f):
    f = pd.Timestamp(f)
    return f"{MESES[f.month]} {f.year}"


try:
    datos = cargar()
except Exception:
    st.error("No se pudo consultar la base de datos. Reintenta en unos segundos (Neon puede estar despertando).")
    st.stop()

meses = sorted(datos.fecha.unique())
st.sidebar.title("Filtros")
st.sidebar.caption("Aplican a las páginas Resumen y Centros.")
i0, i1 = st.sidebar.select_slider(
    "Meses", options=list(range(len(meses))), value=(0, len(meses) - 1), format_func=lambda i: etiqueta_mes(meses[i])
)
cats = sorted(datos.categoria.unique())
sel_cats = st.sidebar.multiselect("Categorías", cats, default=cats)
if st.sidebar.button("Actualizar datos"):
    cargar.clear()
    st.rerun()
st.sidebar.caption(f"Datos hasta {etiqueta_mes(meses[-1])} · {len(datos):,} registros")

f = datos[(datos.fecha >= meses[i0]) & (datos.fecha <= meses[i1]) & (datos.categoria.isin(sel_cats))]

tab1, tab2, tab3, tab4 = st.tabs(["Resumen", "Centros de costo", "Comparación mensual", "Sobre los datos"])

# ---------------- 1. RESUMEN ----------------
with tab1:
    st.header("¿Cómo va la organización?")
    st.caption(f"{etiqueta_mes(meses[i0])} a {etiqueta_mes(meses[i1])}")
    ing, gas, res = f.ingresos.sum(), f.gastos_costos.sum(), f.deficit_excedente.sum()
    c = st.columns(4)
    c[0].metric("Ingresos", money(ing))
    c[1].metric("Gastos y costos", money(gas))
    c[2].metric("Excedente / (Déficit)", money(res, True))
    c[3].metric("Margen", f"{res / ing:.1%}" if ing else "–")

    m = f.groupby("fecha")[["ingresos", "gastos_costos", "deficit_excedente"]].sum().reset_index()
    m[["ingresos", "gastos_costos", "deficit_excedente"]] /= 1e6
    fig = go.Figure()
    fig.add_bar(x=m.fecha, y=m.ingresos, name="Ingresos", marker_color=AZUL)
    fig.add_bar(x=m.fecha, y=m.gastos_costos, name="Gastos y costos", marker_color=GRIS)
    fig.add_scatter(x=m.fecha, y=m.deficit_excedente, name="Excedente / (Déficit)", mode="lines+markers",
                    line=dict(color=VERDE, width=3))
    fig.update_layout(barmode="group", height=380, margin=dict(t=30, b=10), legend=dict(orientation="h", y=1.12),
                      xaxis=dict(tickvals=list(meses), ticktext=[etiqueta_mes(x) for x in meses]), yaxis_title="Millones de $")
    st.subheader("Evolución mensual")
    st.plotly_chart(fig, width="stretch")

    st.subheader("Resultado por categoría")
    cat = f.groupby("categoria")["deficit_excedente"].sum().sort_values().reset_index()
    cat["deficit_excedente"] /= 1e6
    cat["tipo"] = cat.deficit_excedente.gt(0).map({True: "Excedente", False: "Déficit"})
    fig = px.bar(cat, x="deficit_excedente", y="categoria", orientation="h", color="tipo",
                 color_discrete_map={"Excedente": VERDE, "Déficit": ROJO},
                 labels={"deficit_excedente": "Millones de $", "categoria": "", "tipo": ""})
    fig.update_layout(height=340, margin=dict(t=10, b=10))
    st.plotly_chart(fig, width="stretch")

# ---------------- 2. CENTROS ----------------
with tab2:
    st.header("¿Qué centros de costo pesan más?")
    a, b = st.columns([2, 1])
    met = a.radio("Medir por", list(SERIES), horizontal=True)
    n = b.slider("Cuántos mostrar", 5, 25, 10)
    col = SERIES[met]
    g = f.groupby(["codigo_centro", "centro_costo", "categoria"], as_index=False)[
        ["ingresos", "gastos_costos", "deficit_excedente"]].sum()
    if col == "deficit_excedente":
        top = pd.concat([g.nsmallest(n // 2 + n % 2, col), g.nlargest(n // 2, col)]).sort_values(col)
        st.caption("Muestra los mayores déficits (rojo) y los mayores excedentes (verde).")
        colores = top[col].gt(0).map({True: VERDE, False: ROJO})
    else:
        top = g.nlargest(n, col).sort_values(col)
        colores = AZUL
    fig = go.Figure(go.Bar(x=top[col], y=top.centro_costo, orientation="h", marker_color=colores,
                           customdata=top.categoria,
                           hovertemplate="%{y}<br>%{customdata}<br>%{x:$,.0f}<extra></extra>"))
    fig.update_layout(height=max(320, 30 * len(top)), margin=dict(t=10, b=10), yaxis_title=None)
    st.plotly_chart(fig, width="stretch")

    st.subheader("Peso de cada categoría y centro en los gastos y costos")
    tm = g[g.gastos_costos > 0]
    if len(tm):
        fig = px.treemap(tm, path=["categoria", "centro_costo"], values="gastos_costos",
                         color_discrete_sequence=px.colors.qualitative.Safe)
        fig.update_layout(height=450, margin=dict(t=10, b=10))
        st.plotly_chart(fig, width="stretch")

    st.subheader("Detalle")
    q = st.text_input("Buscar centro o código")
    t = g if not q else g[g.centro_costo.str.contains(q, case=False, na=False)
                          | g.codigo_centro.str.contains(q, na=False)]
    st.dataframe(
        t.sort_values("gastos_costos", ascending=False).rename(columns={
            "codigo_centro": "Código", "centro_costo": "Centro", "categoria": "Categoría", "ingresos": "Ingresos",
            "gastos_costos": "Gastos y costos", "deficit_excedente": "Excedente / (Déficit)"}),
        hide_index=True, width="stretch",
        column_config={k: st.column_config.NumberColumn(format="$%,.0f")
                       for k in ["Ingresos", "Gastos y costos", "Excedente / (Déficit)"]})

# ---------------- 3. COMPARACION MENSUAL ----------------
with tab3:
    st.header("¿Cómo cambió mes a mes?")
    st.caption("Esta página usa todas las categorías; los filtros de la izquierda no aplican aquí.")
    k = st.selectbox("Mes a analizar", range(len(meses) - 1, -1, -1), format_func=lambda i: etiqueta_mes(meses[i]))
    act = datos[datos.fecha == meses[k]]
    ant = datos[datos.fecha == meses[k - 1]] if k > 0 else None
    c = st.columns(3)
    for cc, (nom, col) in zip(c, SERIES.items()):
        v = act[col].sum()
        if ant is not None:
            d = v - ant[col].sum()
            cc.metric(nom, money(v), f"{money(d, True)} vs {etiqueta_mes(meses[k - 1])}",
                      delta_color="inverse" if col == "gastos_costos" else "normal")
        else:
            cc.metric(nom, money(v))
    ver = st.multiselect("Series a comparar", list(SERIES), default=["Ingresos", "Gastos y costos"])
    mm = datos.groupby("fecha")[list(SERIES.values())].sum().reset_index()
    mm[list(SERIES.values())] /= 1e6
    fig = go.Figure()
    for s, colr in zip(ver, [AZUL, GRIS, VERDE]):
        fig.add_scatter(x=mm.fecha, y=mm[SERIES[s]], name=s, mode="lines+markers", line=dict(color=colr, width=3))
    fig.add_shape(type="line", x0=meses[k], x1=meses[k], y0=0, y1=1, yref="paper",
                  line=dict(dash="dot", color=GRIS))
    fig.update_layout(height=360, margin=dict(t=10, b=10), xaxis=dict(tickvals=list(meses), ticktext=[etiqueta_mes(x) for x in meses]),
                      legend=dict(orientation="h", y=1.12), yaxis_title="Millones de $")
    st.plotly_chart(fig, width="stretch")

    if ant is not None:
        st.subheader("Qué categorías explican el cambio")
        v = (act.groupby("categoria")["deficit_excedente"].sum()
             .sub(ant.groupby("categoria")["deficit_excedente"].sum(), fill_value=0).sort_values().reset_index())
        v["deficit_excedente"] /= 1e6
        v["tipo"] = v.deficit_excedente.gt(0).map({True: "Mejora", False: "Empeora"})
        fig = px.bar(v, x="deficit_excedente", y="categoria", orientation="h", color="tipo",
                     color_discrete_map={"Mejora": VERDE, "Empeora": ROJO},
                     labels={"deficit_excedente": "Cambio en el resultado (millones de $)", "categoria": "", "tipo": ""})
        fig.update_layout(height=340, margin=dict(t=10, b=10))
        st.plotly_chart(fig, width="stretch")

# ---------------- 4. SOBRE LOS DATOS ----------------
with tab4:
    st.header("Sobre los datos")
    st.markdown(f"""
**Fuente:** informes mensuales de *Centro de Costos* exportados de Biable, 2025. Hoy hay **{len(meses)} meses**
({etiqueta_mes(meses[0])} a {etiqueta_mes(meses[-1])}), **{datos.codigo_centro.nunique()} centros** y {len(datos):,} registros.

**Definiciones**
- **Ingresos** = ingresos operacionales + no operacionales.
- **Gastos y costos** = gastos operacionales + no operacionales + costos.
- **Excedente / (Déficit)** = el valor reportado por Biable (ingresos − gastos − costos).

**Validación:** cada mes se compara contra la fila *TOTAL* de Biable, y los 12 meses cuadran al 100 %.
Para lograrlo se corrigieron 4 valores del centro **020320 CLASES DE COCINA NUTRIR**:
- **Octubre 2025:** traía una copia idéntica de CENA DE GALA (ingresos $20,732,000, gastos $7,490,346.76); el TOTAL de Biable la cuenta una sola vez.
- **Diciembre 2025:** traía un déficit de $200,000 arrastrado de noviembre, sin ingresos ni gastos.

No se pudo confirmar con quien exporta de Biable.

**Categorías:** salen de la hoja de totalización de Biable. El centro GESTAR SSP aparece en dos secciones y se asignó a *Propios de Nutrir*; los centros 200210 y 6010 quedan en *Sin categoría*.
""")
