import streamlit as st
from supabase import create_client
import pandas as pd

st.set_page_config(page_title="Relatório de Baixas", page_icon="📋", layout="wide")

SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]

@st.cache_resource
def get_client():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

sb = get_client()

def fetch_all(table, cols):
    PAGE = 1000
    rows, offset = [], 0
    while True:
        r = sb.table(table).select(cols).range(offset, offset + PAGE - 1).execute()
        rows.extend(r.data)
        if len(r.data) < PAGE:
            break
        offset += PAGE
    return rows

@st.cache_data(ttl=60)
def carregar_baixas():
    r_exec = fetch_all("execucoes",
                       "id, parceiro_id, nome_escola, codigo_inep, municipio, uf, kit, fase, fabricante, data_implantacao")
    r_ei   = fetch_all("execucao_itens", "execucao_id, item_id, qtd")
    r_parc = sb.table("parceiros").select("id, nome").execute().data
    r_item = sb.table("itens").select("id, nome").execute().data

    df_exec = pd.DataFrame(r_exec)
    df_ei   = pd.DataFrame(r_ei)
    df_parc = pd.DataFrame(r_parc).rename(columns={"id": "parceiro_id", "nome": "parceiro"})
    df_item = pd.DataFrame(r_item).rename(columns={"id": "item_id", "nome": "item"})

    df = (df_ei
          .merge(df_exec, left_on="execucao_id", right_on="id")
          .merge(df_parc, on="parceiro_id")
          .merge(df_item, on="item_id"))

    df = df[[
        "parceiro", "fase", "fabricante", "uf", "municipio",
        "nome_escola", "codigo_inep", "kit", "item", "qtd", "data_implantacao"
    ]].rename(columns={
        "parceiro":        "Parceiro",
        "fase":            "Fase",
        "fabricante":      "Fabricante",
        "uf":              "UF",
        "municipio":       "Município",
        "nome_escola":     "Escola",
        "codigo_inep":     "INEP",
        "kit":             "APs",
        "item":            "Item",
        "qtd":             "Qtd Baixada",
        "data_implantacao":"Data",
    })

    df["Qtd Baixada"] = pd.to_numeric(df["Qtd Baixada"], errors="coerce").fillna(0).astype(int)
    df["APs"]         = pd.to_numeric(df["APs"],         errors="coerce").fillna(0).astype(int)
    return df

st.title("📋 Relatório de Baixas por Escola")
st.caption("Itens baixados de estoque por instalação — com INEP para rastreabilidade")

df_base = carregar_baixas()

# ── Filtros ───────────────────────────────────────────────────────────────────
with st.expander("🔎 Filtros", expanded=True):
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        parc_f = st.selectbox("Parceiro", ["Todos"] + sorted(df_base["Parceiro"].dropna().unique().tolist()))
    with col2:
        fase_f = st.selectbox("Fase", ["Todas"] + sorted(df_base["Fase"].dropna().unique().tolist()))
    with col3:
        uf_f   = st.selectbox("UF", ["Todas"] + sorted(df_base["UF"].dropna().unique().tolist()))
    with col4:
        item_f = st.selectbox("Item", ["Todos"] + sorted(df_base["Item"].dropna().unique().tolist()))

    col5, col6 = st.columns(2)
    with col5:
        inep_f = st.text_input("Buscar INEP ou Escola")

df = df_base.copy()
if parc_f != "Todos":   df = df[df["Parceiro"] == parc_f]
if fase_f != "Todas":   df = df[df["Fase"] == fase_f]
if uf_f   != "Todas":   df = df[df["UF"] == uf_f]
if item_f != "Todos":   df = df[df["Item"] == item_f]
if inep_f:
    mask = (df["INEP"].astype(str).str.contains(inep_f, case=False, na=False) |
            df["Escola"].str.contains(inep_f, case=False, na=False))
    df = df[mask]

# ── KPIs ──────────────────────────────────────────────────────────────────────
k1, k2, k3, k4 = st.columns(4)
k1.metric("Escolas únicas",    df["INEP"].nunique())
k2.metric("Registros de baixa", len(df))
k3.metric("Total de unidades",  int(df["Qtd Baixada"].sum()))
k4.metric("Parceiros",          df["Parceiro"].nunique())

st.markdown("---")

# ── Tabela ────────────────────────────────────────────────────────────────────
st.dataframe(df, use_container_width=True, hide_index=True, height=520)

st.download_button(
    "⬇️ Exportar (.csv)",
    data=df.to_csv(index=False).encode("utf-8"),
    file_name="relatorio_baixas.csv",
    mime="text/csv",
)

st.markdown("---")

# ── Resumo por Parceiro × Item ────────────────────────────────────────────────
st.subheader("Resumo por Parceiro × Fase × Item")
df_res = (df.groupby(["Parceiro", "Fase", "Item"])["Qtd Baixada"]
            .sum()
            .reset_index()
            .sort_values(["Parceiro", "Fase", "Qtd Baixada"], ascending=[True, True, False]))
st.dataframe(df_res, use_container_width=True, hide_index=True, height=350)
