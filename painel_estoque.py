import streamlit as st
from supabase import create_client
import pandas as pd
import plotly.express as px

# ── Configuração ──────────────────────────────────────────────────────────────
SUPABASE_URL = "https://dnchdssuifhibbquhqkg.supabase.co"
SUPABASE_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
    ".eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImRuY2hkc3N1aWZoaWJicXVocWtnIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODAzMTY5NjEsImV4cCI6MjA5NTg5Mjk2MX0"
    ".70QbG8dX1s5b5pH18jB2ehBTg8FVZMDiXZJPE9sCuKw"
)

st.set_page_config(
    page_title="Controle de Estoque",
    page_icon="📦",
    layout="wide",
)

# ── Carrega dados ─────────────────────────────────────────────────────────────
@st.cache_data(ttl=60)
def carregar_saldo():
    sb = create_client(SUPABASE_URL, SUPABASE_KEY)
    resp = sb.table("vw_saldo").select("*").execute()
    df = pd.DataFrame(resp.data)
    # garante tipos numéricos
    for col in ["total_recebido", "total_baixado",
                "total_recebido_transferencia",
                "total_enviado_transferencia", "saldo_atual"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
    return df

df_base = carregar_saldo()

# ── Sidebar ───────────────────────────────────────────────────────────────────
st.sidebar.image(
    "https://em-content.zobj.net/source/microsoft-teams/363/package_1f4e6.png",
    width=60,
)
st.sidebar.title("Filtros")

parceiros_lista = ["Todos"] + sorted(df_base["parceiro"].dropna().unique().tolist())
fases_lista     = ["Todas"] + sorted(df_base["fase"].dropna().unique().tolist())
fabr_lista      = ["Todos"] + sorted(df_base["fabricante"].dropna().unique().tolist())

parceiro_sel = st.sidebar.selectbox("Parceiro", parceiros_lista)
fase_sel     = st.sidebar.selectbox("Fase",     fases_lista)
fabr_sel     = st.sidebar.selectbox("Fabricante", fabr_lista)

st.sidebar.markdown("---")
mostrar_negativos = st.sidebar.checkbox("⚠️ Mostrar apenas saldo negativo", value=False)
st.sidebar.caption("Dados atualizados a cada 60 s")

# ── Aplica filtros ────────────────────────────────────────────────────────────
df = df_base.copy()
if parceiro_sel != "Todos":
    df = df[df["parceiro"] == parceiro_sel]
if fase_sel != "Todas":
    df = df[df["fase"] == fase_sel]
if fabr_sel != "Todos":
    df = df[df["fabricante"] == fabr_sel]
if mostrar_negativos:
    df = df[df["saldo_atual"] < 0]

# ── Título ────────────────────────────────────────────────────────────────────
st.title("📦 Controle de Estoque — Painel Online")
st.caption("Fase 4.2 · Saldos calculados em tempo real a partir de compras, instalações e transferências")

# ── KPIs ──────────────────────────────────────────────────────────────────────
c1, c2, c3, c4 = st.columns(4)
total_rec  = int(df["total_recebido"].sum())
total_bai  = int(df["total_baixado"].sum())
total_sal  = int(df["saldo_atual"].sum())
n_neg      = int((df["saldo_atual"] < 0).sum())

c1.metric("Total Recebido",       f"{total_rec:,}".replace(",", "."))
c2.metric("Total Baixado (inst.)",f"{total_bai:,}".replace(",", "."))
c3.metric("Saldo Geral",          f"{total_sal:,}".replace(",", "."))
c4.metric("Linhas c/ Saldo Neg.", n_neg, delta=("⚠️ Atenção" if n_neg > 0 else None),
          delta_color="inverse")

st.markdown("---")

# ── Tabela principal ──────────────────────────────────────────────────────────
st.subheader("Saldo por Parceiro × Item")

rename = {
    "parceiro":                    "Parceiro",
    "item":                        "Item",
    "fabricante":                  "Fabricante",
    "fase":                        "Fase",
    "total_recebido":              "Recebido",
    "total_baixado":               "Baixado",
    "total_recebido_transferencia":"Transf. Recebida",
    "total_enviado_transferencia": "Transf. Enviada",
    "saldo_atual":                 "Saldo Atual",
}
df_show = df[list(rename.keys())].rename(columns=rename)

def colorir(val):
    if isinstance(val, (int, float)):
        if val < 0:
            return "background-color:#ffcccc; color:#990000; font-weight:bold"
        if val == 0:
            return "color:#888888"
    return ""

st.dataframe(
    df_show.style.map(colorir, subset=["Saldo Atual"]),
    use_container_width=True,
    hide_index=True,
    height=420,
)

st.download_button(
    "⬇️ Exportar tabela (.csv)",
    data=df_show.to_csv(index=False).encode("utf-8"),
    file_name="saldo_estoque.csv",
    mime="text/csv",
)

st.markdown("---")

# ── Gráficos ──────────────────────────────────────────────────────────────────
col_graf1, col_graf2 = st.columns(2)

with col_graf1:
    st.subheader("Saldo por Item (total)")
    df_item = (
        df.groupby("item")["saldo_atual"]
        .sum()
        .reset_index()
        .sort_values("saldo_atual", ascending=True)
    )
    fig1 = px.bar(
        df_item, x="saldo_atual", y="item", orientation="h",
        color="saldo_atual",
        color_continuous_scale=["#d62728", "#ffdd57", "#2ca02c"],
        labels={"saldo_atual": "Saldo", "item": "Item"},
        height=500,
    )
    fig1.update_layout(coloraxis_showscale=False, margin=dict(l=0, r=0, t=20, b=0))
    st.plotly_chart(fig1, use_container_width=True)

with col_graf2:
    st.subheader("Recebido vs Baixado por Parceiro")
    df_parc = df.groupby("parceiro")[["total_recebido", "total_baixado"]].sum().reset_index()
    df_melt = df_parc.melt(id_vars="parceiro", var_name="Tipo", value_name="Qtd")
    df_melt["Tipo"] = df_melt["Tipo"].map(
        {"total_recebido": "Recebido", "total_baixado": "Baixado (inst.)"}
    )
    fig2 = px.bar(
        df_melt, x="parceiro", y="Qtd", color="Tipo",
        barmode="group",
        color_discrete_map={"Recebido": "#1f77b4", "Baixado (inst.)": "#ff7f0e"},
        labels={"parceiro": "Parceiro", "Qtd": "Quantidade"},
        height=500,
    )
    fig2.update_layout(margin=dict(l=0, r=0, t=20, b=0))
    st.plotly_chart(fig2, use_container_width=True)

# ── Alerta saldo negativo ─────────────────────────────────────────────────────
df_neg = df_base[df_base["saldo_atual"] < 0][["parceiro", "item", "saldo_atual"]]
if not df_neg.empty:
    st.markdown("---")
    st.warning(f"⚠️ **{len(df_neg)} linha(s) com saldo negativo detectada(s):**")
    st.dataframe(
        df_neg.rename(columns={"parceiro":"Parceiro","item":"Item","saldo_atual":"Saldo"}),
        use_container_width=True, hide_index=True
    )
