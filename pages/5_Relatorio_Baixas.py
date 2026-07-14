import re
import streamlit as st
import plotly.express as px
from supabase import create_client
import pandas as pd
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from utils.tema_iuh import aplicar_tema, sidebar_logo, page_header

st.set_page_config(page_title="Relatório de Baixas", page_icon="📋", layout="wide")
aplicar_tema()
sidebar_logo("Relatório de Baixas")

SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]

@st.cache_resource
def get_client():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

sb = get_client()

# Mapeamento item nome → função
FUNCAO_MAP = {
    'AP':           ['EAP', 'DM-AP 610', ' AP ', 'AP 360', 'AP 610', 'AP 1800', 'AP 3620'],
    'ROTEADOR':     ['ROUTER', 'ROTEADOR', 'ER7212', 'ER605', 'DM-AP GT',
                     'R3005G', 'R3006G', 'R3010G'],
    'SWITCH':       ['SWITCH'],
    'CONTROLADORA': ['OC200', 'OC300', 'CONTROLLER', 'CONTROLADORA'],
    'INJETOR':      ['INJETOR', 'INJECTOR', 'POE'],
    'SIMET':        ['SIMET'],
    'NOBREAK':      ['NOBREAK'],
    'RACK 5U':      ['RACK 5U'],
    'RACK 8U':      ['RACK 8U'],
    'ORGANIZADOR':  ['ORGANIZADOR'],
    'BANDEJA':      ['BANDEJA'],
    'CABO':         ['CABO'],
}

def get_funcao(item_nome):
    nome = str(item_nome).upper()
    for funcao, kws in FUNCAO_MAP.items():
        for kw in kws:
            if kw in nome:
                return funcao
    return 'OUTROS'

def parse_kit_num(kit_str):
    if kit_str is None:
        return None
    s = str(kit_str).strip()
    m = re.search(r'KIT\s+0*(\d+)', s, re.IGNORECASE)
    if m:
        return int(m.group(1))
    m2 = re.fullmatch(r'\d+', s)
    if m2:
        return int(s)
    return None

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
                       "id, parceiro_id, nome_escola, codigo_inep, municipio, uf, kit, fase, data_implantacao")
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

    df["Função"] = df["item"].apply(get_funcao)

    df = df[[
        "parceiro", "fase", "uf", "municipio",
        "nome_escola", "codigo_inep", "kit", "Função", "item", "qtd", "data_implantacao"
    ]].rename(columns={
        "parceiro":        "Parceiro",
        "fase":            "Fase",
        "uf":              "UF",
        "municipio":       "Município",
        "nome_escola":     "Escola",
        "codigo_inep":     "INEP",
        "kit":             "Kit",
        "item":            "Item",
        "qtd":             "Qtd Baixada",
        "data_implantacao":"Data",
    })

    df["Qtd Baixada"] = pd.to_numeric(df["Qtd Baixada"], errors="coerce").fillna(0)
    df["kit_num"]     = df["Kit"].apply(parse_kit_num)
    return df

page_header("📋 Relatório de Baixas por Escola",
            "Itens baixados de estoque por instalação — com INEP para rastreabilidade")

df_base = carregar_baixas()

# ── Filtros ───────────────────────────────────────────────────────────────────
with st.expander("🔎 Filtros", expanded=True):
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        parc_f  = st.selectbox("Parceiro", ["Todos"] + sorted(df_base["Parceiro"].dropna().unique().tolist()))
    with col2:
        fase_f  = st.selectbox("Fase", ["Todas"] + sorted(df_base["Fase"].dropna().unique().tolist()))
    with col3:
        uf_f    = st.selectbox("UF", ["Todas"] + sorted(df_base["UF"].dropna().unique().tolist()))
    with col4:
        func_f  = st.selectbox("Função", ["Todas"] + sorted(df_base["Função"].dropna().unique().tolist()))

    col5, col6 = st.columns(2)
    with col5:
        item_f  = st.selectbox("Item específico", ["Todos"] + sorted(df_base["Item"].dropna().unique().tolist()))
    with col6:
        inep_f  = st.text_input("Buscar INEP ou Escola")

df = df_base.copy()
if parc_f != "Todos":  df = df[df["Parceiro"] == parc_f]
if fase_f != "Todas":  df = df[df["Fase"] == fase_f]
if uf_f   != "Todas":  df = df[df["UF"] == uf_f]
if func_f != "Todas":  df = df[df["Função"] == func_f]
if item_f != "Todos":  df = df[df["Item"] == item_f]
if inep_f:
    mask = (df["INEP"].astype(str).str.contains(inep_f, case=False, na=False) |
            df["Escola"].str.contains(inep_f, case=False, na=False))
    df = df[mask]

# ── KPIs ──────────────────────────────────────────────────────────────────────
k1, k2, k3, k4 = st.columns(4)
k1.metric("Escolas únicas",     df["INEP"].nunique())
k2.metric("Registros de baixa", len(df))
k3.metric("Total de unidades",  int(df["Qtd Baixada"].sum()))
k4.metric("Parceiros",          df["Parceiro"].nunique())

st.markdown("---")

# ── Abas ──────────────────────────────────────────────────────────────────────
tab1, tab2, tab3 = st.tabs([
    "📋 Tabela de Baixas",
    "📊 Resumo por Parceiro / Função",
    "📈 Consumo de Cabo por AP",
])

# ══════════════════════════════════════════════════════════════════════════════
with tab1:
    cols_display = ["Parceiro","Fase","UF","Município","Escola","INEP","Kit","Função","Item","Qtd Baixada","Data"]
    st.dataframe(df[cols_display], use_container_width=True, hide_index=True, height=480)

    st.download_button(
        "⬇️ Exportar (.csv)",
        data=df[cols_display].to_csv(index=False).encode("utf-8"),
        file_name="relatorio_baixas.csv",
        mime="text/csv",
    )

# ══════════════════════════════════════════════════════════════════════════════
with tab2:
    sub1, sub2 = st.tabs(["Por Parceiro × Fase × Item", "Por Função"])

    with sub1:
        df_res = (df.groupby(["Parceiro", "Fase", "Função", "Item"])["Qtd Baixada"]
                    .sum().reset_index()
                    .sort_values(["Parceiro", "Fase", "Função", "Qtd Baixada"],
                                  ascending=[True, True, True, False]))
        st.dataframe(df_res, use_container_width=True, hide_index=True, height=420)

    with sub2:
        df_func = (df.groupby(["Função", "Item"])["Qtd Baixada"]
                     .sum().reset_index()
                     .sort_values(["Função", "Qtd Baixada"], ascending=[True, False]))
        st.dataframe(df_func, use_container_width=True, hide_index=True, height=420)

# ══════════════════════════════════════════════════════════════════════════════
with tab3:
    st.subheader("Consumo Médio de Cabo por AP")
    st.caption("Metros de cabo baixado ÷ total de APs instalados, por Parceiro e Fase")

    # Filtra somente linhas de CABO (usando dados filtrados da página)
    df_cabo = df[df["Função"] == "CABO"].copy()

    if df_cabo.empty:
        st.info("Nenhum registro de CABO encontrado para os filtros selecionados.")
    else:
        # ── KPIs de cabo ──────────────────────────────────────────────────────
        # APs únicos por INEP (evita dupla contagem pois há múltiplos itens por escola)
        df_aps_inep = df.drop_duplicates("INEP")[["INEP", "Parceiro", "Fase", "kit_num"]].copy()
        df_aps_inep["kit_num"] = pd.to_numeric(df_aps_inep["kit_num"], errors="coerce").fillna(0)

        total_metros = df_cabo["Qtd Baixada"].sum()
        total_aps    = df_aps_inep["kit_num"].sum()
        media_geral  = total_metros / total_aps if total_aps > 0 else 0

        ck1, ck2, ck3 = st.columns(3)
        ck1.metric("Total metros de cabo", f"{int(total_metros):,} m")
        ck2.metric("Total APs (base kit)", f"{int(total_aps):,}")
        ck3.metric("Média geral metros/AP", f"{media_geral:.1f} m")

        st.markdown("---")

        # ── Agrupamento por Parceiro × Fase ──────────────────────────────────
        # Metros de cabo por INEP
        df_cabo_inep = (df_cabo.groupby(["INEP", "Parceiro", "Fase"])["Qtd Baixada"]
                                .sum().reset_index()
                                .rename(columns={"Qtd Baixada": "metros_cabo"}))

        # APs por INEP (único)
        df_cabo_inep = df_cabo_inep.merge(
            df_aps_inep[["INEP","kit_num"]].rename(columns={"kit_num":"aps"}),
            on="INEP", how="left"
        )
        df_cabo_inep["aps"] = pd.to_numeric(df_cabo_inep["aps"], errors="coerce").fillna(0)

        df_grupo = (df_cabo_inep.groupby(["Parceiro", "Fase"])
                                 .agg(
                                     total_metros=("metros_cabo", "sum"),
                                     total_aps=("aps", "sum"),
                                     escolas=("INEP", "nunique"),
                                 ).reset_index())
        df_grupo["metros_por_ap"] = (
            df_grupo["total_metros"] / df_grupo["total_aps"].replace(0, float("nan"))
        ).round(1)
        df_grupo["label"] = df_grupo["Parceiro"] + " · " + df_grupo["Fase"]
        df_grupo = df_grupo.sort_values("metros_por_ap", ascending=False)

        # ── Gráfico ───────────────────────────────────────────────────────────
        fig = px.bar(
            df_grupo,
            x="label",
            y="metros_por_ap",
            color="Fase",
            text="metros_por_ap",
            labels={"label": "", "metros_por_ap": "Metros de cabo / AP"},
            color_discrete_sequence=["#0C6679", "#2EDBA0", "#0a4a5a", "#5ab4c5"],
            height=440,
        )
        fig.update_traces(texttemplate="%{text:.1f} m", textposition="outside")
        fig.update_xaxes(tickangle=40)
        fig.update_layout(
            margin=dict(l=0, r=0, t=20, b=150),
            showlegend=True,
            plot_bgcolor="white",
            yaxis=dict(gridcolor="#e2e8f0"),
        )
        st.plotly_chart(fig, use_container_width=True)

        # ── Tabela de detalhes ────────────────────────────────────────────────
        st.markdown("**Detalhamento por Parceiro × Fase**")
        df_show = df_grupo[["Parceiro","Fase","escolas","total_metros","total_aps","metros_por_ap"]].copy()
        df_show.columns = ["Parceiro","Fase","Escolas","Total Metros","Total APs","Metros/AP"]
        st.dataframe(df_show, use_container_width=True, hide_index=True)
