import streamlit as st
from supabase import create_client
import pandas as pd
import plotly.express as px
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from utils.tema_iuh import aplicar_tema, sidebar_logo, page_header

# ── Configuração ──────────────────────────────────────────────────────────────
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]

st.set_page_config(
    page_title="Controle de Estoque",
    page_icon="📦",
    layout="wide",
)
aplicar_tema()

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

@st.cache_data(ttl=60)
def carregar_consumo_cabo():
    sb = create_client(SUPABASE_URL, SUPABASE_KEY)

    # Itens AP (qualquer item cujo nome contenha as palavras-chave de AP)
    AP_KWS = ['EAP','AP 3620','AP RW','DM-AP','AP361','AP650','AP613','AP 610']
    itens_resp = sb.table('itens').select('id,nome').execute().data
    ap_ids  = [i['id'] for i in itens_resp
               if any(kw in i['nome'].upper() for kw in AP_KWS)]
    cabo_ids = [i['id'] for i in itens_resp
                if i['nome'].upper().strip() == 'CABO'
                or i['nome'].upper().strip().startswith('CABO ')]

    # Parceiros
    parc_resp = sb.table('parceiros').select('id,nome').execute().data
    parc_map  = {p['id']: p['nome'] for p in parc_resp}

    # Execuções (id, fase, inep, parceiro_id)
    exec_rows, offset = [], 0
    while True:
        r = sb.table('execucoes').select('id,fase,codigo_inep,parceiro_id').range(offset, offset + 999).execute()
        exec_rows.extend(r.data)
        if len(r.data) < 1000: break
        offset += 1000
    df_exec = pd.DataFrame(exec_rows).rename(columns={'id': 'execucao_id'})
    df_exec['parceiro'] = df_exec['parceiro_id'].map(parc_map)
    df_exec['fase'] = df_exec['fase'].astype(str).str.strip()

    # Normaliza fase para rótulos limpos
    def norm_fase(f):
        f = f.upper()
        if '4.2 ADICIONAL' in f or 'ADICIONAL' in f: return '4.2 Adicional'
        if '4.2' in f: return '4.2'
        if '4.1' in f: return '4.1'
        if '5.0' in f or '5' in f: return '5.0'
        return f
    df_exec['fase'] = df_exec['fase'].apply(norm_fase)

    exec_id_set = set(df_exec['id'].tolist())

    # Execucao_itens — APs
    ap_rows, offset = [], 0
    while True:
        r = (sb.table('execucao_itens').select('execucao_id,qtd')
               .in_('item_id', ap_ids).range(offset, offset + 999).execute())
        ap_rows.extend(r.data)
        if len(r.data) < 1000: break
        offset += 1000
    df_ap = pd.DataFrame(ap_rows) if ap_rows else pd.DataFrame(columns=['execucao_id','qtd'])
    df_ap['qtd'] = pd.to_numeric(df_ap['qtd'], errors='coerce').fillna(0)
    df_ap_sum = df_ap.groupby('execucao_id')['qtd'].sum().reset_index().rename(columns={'qtd':'total_aps'})

    # Execucao_itens — CABO (metros)
    cabo_rows, offset = [], 0
    while True:
        r = (sb.table('execucao_itens').select('execucao_id,qtd')
               .in_('item_id', cabo_ids).range(offset, offset + 999).execute())
        cabo_rows.extend(r.data)
        if len(r.data) < 1000: break
        offset += 1000
    df_cabo = pd.DataFrame(cabo_rows) if cabo_rows else pd.DataFrame(columns=['execucao_id','qtd'])
    df_cabo['qtd'] = pd.to_numeric(df_cabo['qtd'], errors='coerce').fillna(0)
    df_cabo_sum = df_cabo.groupby('execucao_id')['qtd'].sum().reset_index().rename(columns={'qtd':'total_cabo'})

    # Junta tudo em execuções
    df = df_exec.merge(df_ap_sum,   on='execucao_id', how='left')
    df = df.merge(df_cabo_sum, on='execucao_id', how='left')
    df[['total_aps','total_cabo']] = df[['total_aps','total_cabo']].fillna(0)

    # Agrega por parceiro + fase
    grp = df.groupby(['parceiro','fase'], dropna=False).agg(
        n_escolas  = ('codigo_inep', 'nunique'),
        total_aps  = ('total_aps',  'sum'),
        total_cabo = ('total_cabo', 'sum'),
    ).reset_index()

    grp['media_ap_por_inep']  = (grp['total_aps']  / grp['n_escolas'].replace(0, pd.NA)).round(2)
    grp['media_cabo_por_ap']  = (grp['total_cabo'] / grp['total_aps'].replace(0, pd.NA)).round(1)

    return grp

# ── Sidebar ───────────────────────────────────────────────────────────────────
st.sidebar.image(
    "https://em-content.zobj.net/source/microsoft-teams/363/package_1f4e6.png",
    width=60,
)
sidebar_logo("Painel de Estoque")

parceiros_lista = ["Todos"] + sorted(df_base["parceiro"].dropna().unique().tolist())
fases_lista     = ["Todas"] + sorted(df_base["fase"].dropna().unique().tolist())
fabr_lista      = ["Todos"] + sorted(df_base["fabricante"].dropna().unique().tolist())

itens_lista  = ["Todos"] + sorted(df_base["item"].dropna().unique().tolist())

parceiro_sel = st.sidebar.selectbox("Parceiro",    parceiros_lista)
fase_sel     = st.sidebar.selectbox("Fase",        fases_lista)
fabr_sel     = st.sidebar.selectbox("Fabricante",  fabr_lista)
item_sel     = st.sidebar.selectbox("Item",        itens_lista)

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
if item_sel != "Todos":
    df = df[df["item"] == item_sel]
if mostrar_negativos:
    df = df[df["saldo_atual"] < 0]

# ── Título ────────────────────────────────────────────────────────────────────
page_header("📦 Controle de Estoque — Painel Online", "Fase 4.2 · Saldos calculados em tempo real a partir de compras, instalações e transferências")

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

# ── Consumo de cabo por AP ───────────────────────────────────────────────────
st.markdown("---")
st.subheader("📡 Consumo de Cabo por AP — por Parceiro e Fase")

df_cabo_ap = carregar_consumo_cabo()

# Aplica os mesmos filtros da sidebar
df_cabo_fil = df_cabo_ap.copy()
if parceiro_sel != "Todos":
    df_cabo_fil = df_cabo_fil[df_cabo_fil["parceiro"] == parceiro_sel]
if fase_sel != "Todas":
    df_cabo_fil = df_cabo_fil[df_cabo_fil["fase"] == fase_sel]

df_cabo_show = df_cabo_fil.rename(columns={
    "parceiro":          "Parceiro",
    "fase":              "Fase",
    "n_escolas":         "Escolas (INEPs)",
    "total_aps":         "Total APs Instalados",
    "total_cabo":        "Total Cabo (m)",
    "media_ap_por_inep": "Média APs / INEP",
    "media_cabo_por_ap": "Média Cabo / AP (m)",
}).sort_values(["Fase","Parceiro"])

df_cabo_show["Total APs Instalados"] = df_cabo_show["Total APs Instalados"].astype(int)
df_cabo_show["Total Cabo (m)"]       = df_cabo_show["Total Cabo (m)"].astype(int)

st.dataframe(
    df_cabo_show,
    use_container_width=True,
    hide_index=True,
    height=min(60 + len(df_cabo_show) * 35, 500),
    column_config={
        "Média APs / INEP":    st.column_config.NumberColumn(format="%.2f"),
        "Média Cabo / AP (m)": st.column_config.NumberColumn(format="%.1f m"),
        "Total Cabo (m)":      st.column_config.NumberColumn(format="%d m"),
    }
)

st.download_button(
    "⬇️ Exportar consumo cabo (.csv)",
    data=df_cabo_show.to_csv(index=False).encode("utf-8"),
    file_name="consumo_cabo_por_ap.csv",
    mime="text/csv",
)

# ── Alerta saldo negativo ─────────────────────────────────────────────────────
df_neg = df_base[df_base["saldo_atual"] < 0][["parceiro", "item", "saldo_atual"]]
if not df_neg.empty:
    st.markdown("---")
    st.warning(f"⚠️ **{len(df_neg)} linha(s) com saldo negativo detectada(s):**")
    st.dataframe(
        df_neg.rename(columns={"parceiro":"Parceiro","item":"Item","saldo_atual":"Saldo"}),
        use_container_width=True, hide_index=True
    )
