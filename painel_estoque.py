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
    for col in ["total_recebido", "total_baixado",
                "total_recebido_transferencia",
                "total_enviado_transferencia", "saldo_atual"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
    return df

@st.cache_data(ttl=60)
def carregar_parceiros_uf():
    sb = create_client(SUPABASE_URL, SUPABASE_KEY)
    r = sb.table("parceiros").select("nome, uf").execute()
    return {p["nome"]: (p.get("uf") or "N/D") for p in r.data}

@st.cache_data(ttl=60)
def carregar_consumo_cabo():
    sb = create_client(SUPABASE_URL, SUPABASE_KEY)

    AP_KWS = ['EAP','AP 3620','AP RW','DM-AP','AP361','AP650','AP613','AP 610']
    itens_resp = sb.table('itens').select('id,nome').execute().data
    ap_ids  = [i['id'] for i in itens_resp
               if any(kw in i['nome'].upper() for kw in AP_KWS)]
    cabo_ids = [i['id'] for i in itens_resp
                if i['nome'].upper().strip() == 'CABO'
                or i['nome'].upper().strip().startswith('CABO ')]

    parc_resp = sb.table('parceiros').select('id,nome').execute().data
    parc_map  = {p['id']: p['nome'] for p in parc_resp}

    exec_rows, offset = [], 0
    while True:
        r = sb.table('execucoes').select('id,fase,codigo_inep,parceiro_id').range(offset, offset + 999).execute()
        exec_rows.extend(r.data)
        if len(r.data) < 1000: break
        offset += 1000
    df_exec = pd.DataFrame(exec_rows).rename(columns={'id': 'execucao_id'})
    df_exec['parceiro'] = df_exec['parceiro_id'].map(parc_map)
    df_exec['fase'] = df_exec['fase'].astype(str).str.strip()

    def norm_fase(f):
        f = f.upper()
        if '4.2 ADICIONAL' in f or 'ADICIONAL' in f: return '4.2 Adicional'
        if '4.2' in f: return '4.2'
        if '4.1' in f: return '4.1'
        if '5.0' in f or '5' in f: return '5.0'
        return f
    df_exec['fase'] = df_exec['fase'].apply(norm_fase)

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

    df = df_exec.merge(df_ap_sum,   on='execucao_id', how='left')
    df = df.merge(df_cabo_sum, on='execucao_id', how='left')
    df[['total_aps','total_cabo']] = df[['total_aps','total_cabo']].fillna(0)

    grp = df.groupby(['parceiro','fase'], dropna=False).agg(
        n_escolas  = ('codigo_inep', 'nunique'),
        total_aps  = ('total_aps',  'sum'),
        total_cabo = ('total_cabo', 'sum'),
    ).reset_index()

    grp['media_ap_por_inep'] = (grp['total_aps']  / grp['n_escolas'].replace(0, pd.NA)).round(2)
    grp['media_cabo_por_ap'] = (grp['total_cabo'] / grp['total_aps'].replace(0, pd.NA)).round(1)

    return grp

@st.cache_data(ttl=60)
def carregar_financeiro_estoque():
    sb = create_client(SUPABASE_URL, SUPABASE_KEY)

    parc_rows = sb.table("parceiros").select("id,nome").execute().data
    item_rows = sb.table("itens").select("id,nome").execute().data
    parc_map  = {p["id"]: p["nome"] for p in parc_rows}
    item_map  = {i["id"]: i["nome"] for i in item_rows}

    # Compras: valor comprado = qtd_recebida × valor_unitario
    comp = sb.table("compras").select(
        "parceiro_id,item_id,fase,qtd_recebida,valor_unitario"
    ).execute().data
    df_c = pd.DataFrame(comp) if comp else pd.DataFrame(
        columns=["parceiro_id","item_id","fase","qtd_recebida","valor_unitario"])
    df_c["qtd_recebida"]  = pd.to_numeric(df_c["qtd_recebida"],  errors="coerce").fillna(0)
    df_c["valor_unitario"]= pd.to_numeric(df_c["valor_unitario"], errors="coerce").fillna(0)
    df_c["valor_comprado"]= df_c["qtd_recebida"] * df_c["valor_unitario"]
    df_c["parceiro"]      = df_c["parceiro_id"].map(parc_map)
    df_c["item"]          = df_c["item_id"].map(item_map)
    df_c["fase"]          = df_c["fase"].astype(str).str.strip()

    # Custo médio por (item_id, fase) — usado para valorizar saldo e transferências
    def _wmean(g):
        tot_qtd = g["qtd_recebida"].sum()
        return (g["valor_comprado"].sum() / tot_qtd) if tot_qtd > 0 else 0.0
    unit_cost = df_c.groupby(["item_id","fase"]).apply(_wmean).to_dict()

    # Transferências: valoriza com custo médio do item
    transf = sb.table("transferencias").select(
        "parceiro_origem_id,parceiro_destino_id,item_id,qtd,fase,status"
    ).execute().data
    df_t = pd.DataFrame(transf) if transf else pd.DataFrame(
        columns=["parceiro_origem_id","parceiro_destino_id","item_id","qtd","fase","status"])
    df_t["qtd"] = pd.to_numeric(df_t["qtd"], errors="coerce").fillna(0)
    df_t["fase"] = df_t["fase"].astype(str).str.strip()
    df_t["custo_unit"] = df_t.apply(
        lambda r: unit_cost.get((r["item_id"], r["fase"]),
                  unit_cost.get((r["item_id"], ""), 0.0)), axis=1)
    df_t["valor_transf"] = df_t["qtd"] * df_t["custo_unit"]
    df_t["origem"]  = df_t["parceiro_origem_id"].map(parc_map)
    df_t["destino"] = df_t["parceiro_destino_id"].map(parc_map)

    return df_c, df_t, unit_cost

df_base = carregar_saldo()
parc_uf = carregar_parceiros_uf()

# ── Sidebar ───────────────────────────────────────────────────────────────────
st.sidebar.image(
    "https://em-content.zobj.net/source/microsoft-teams/363/package_1f4e6.png",
    width=60,
)
sidebar_logo("Painel Estoque")

parceiros_lista = ["Todos"] + sorted(df_base["parceiro"].dropna().unique().tolist())
fases_lista     = ["Todas"] + sorted(df_base["fase"].dropna().unique().tolist())
fabr_lista      = ["Todos"] + sorted(df_base["fabricante"].dropna().unique().tolist())
itens_lista     = ["Todos"] + sorted(df_base["item"].dropna().unique().tolist())

parceiro_sel = st.sidebar.selectbox("Parceiro",   parceiros_lista)
fase_sel     = st.sidebar.selectbox("Fase",       fases_lista)
fabr_sel     = st.sidebar.selectbox("Fabricante", fabr_lista)
item_sel     = st.sidebar.selectbox("Item",       itens_lista)

st.sidebar.markdown("---")
mostrar_negativos = st.sidebar.checkbox("⚠️ Mostrar apenas saldo negativo", value=False)
st.sidebar.caption("Dados atualizados a cada 60 s")

# ── Aplica filtros (tabela 1 — por fase) ──────────────────────────────────────
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
page_header("📦 Controle de Estoque — Painel Online",
            "Saldos calculados em tempo real a partir de compras, instalações e transferências")

num_cols = ["total_recebido","total_baixado",
            "total_recebido_transferencia","total_enviado_transferencia","saldo_atual"]

def colorir(val):
    if isinstance(val, (int, float)):
        if val < 0:  return "background-color:#ffcccc; color:#990000; font-weight:bold"
        if val == 0: return "color:#888888"
    return ""

# ═════════════════════════════════════════════════════════════════════════════
# VISÃO 1 — POR FASE
# ═════════════════════════════════════════════════════════════════════════════
st.markdown("### 📋 Visão por Fase")
st.caption("Filtros da sidebar aplicados (parceiro, fase, fabricante, item)")

c1, c2, c3, c4 = st.columns(4)
c1.metric("Total Recebido",           f"{int(df['total_recebido'].sum()):,}".replace(",","."))
c2.metric("Total Baixado (inst.)",    f"{int(df['total_baixado'].sum()):,}".replace(",","."))
c3.metric("Saldo (fase selecionada)", f"{int(df['saldo_atual'].sum()):,}".replace(",","."))
n_neg1 = int((df["saldo_atual"] < 0).sum())
c4.metric("Linhas c/ Saldo Neg.", n_neg1,
          delta=("⚠️ Atenção" if n_neg1 > 0 else None), delta_color="inverse")

st.subheader("Saldo por Parceiro × Item (por fase)")

rename1 = {
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
df_show1 = df[list(rename1.keys())].rename(columns=rename1)

st.dataframe(
    df_show1.style.map(colorir, subset=["Saldo Atual"]),
    use_container_width=True, hide_index=True, height=420,
)
st.download_button(
    "⬇️ Exportar tabela por fase (.csv)",
    data=df_show1.to_csv(index=False).encode("utf-8"),
    file_name="saldo_por_fase.csv",
    mime="text/csv",
)

col_graf1, col_graf2 = st.columns(2)
with col_graf1:
    st.subheader("Saldo por Item")
    df_item = df.groupby("item")["saldo_atual"].sum().reset_index().sort_values("saldo_atual")
    fig1 = px.bar(df_item, x="saldo_atual", y="item", orientation="h",
                  color="saldo_atual",
                  color_continuous_scale=["#d62728","#ffdd57","#2ca02c"],
                  labels={"saldo_atual":"Saldo","item":"Item"}, height=420)
    fig1.update_layout(coloraxis_showscale=False, margin=dict(l=0,r=0,t=20,b=0))
    st.plotly_chart(fig1, use_container_width=True)

with col_graf2:
    st.subheader("Recebido vs Baixado por Parceiro")
    df_parc = df.groupby("parceiro")[["total_recebido","total_baixado"]].sum().reset_index()
    df_melt = df_parc.melt(id_vars="parceiro", var_name="Tipo", value_name="Qtd")
    df_melt["Tipo"] = df_melt["Tipo"].map({"total_recebido":"Recebido","total_baixado":"Baixado (inst.)"})
    fig2 = px.bar(df_melt, x="parceiro", y="Qtd", color="Tipo", barmode="group",
                  color_discrete_map={"Recebido":"#1f77b4","Baixado (inst.)":"#ff7f0e"},
                  labels={"parceiro":"Parceiro","Qtd":"Quantidade"}, height=420)
    fig2.update_layout(margin=dict(l=0,r=0,t=20,b=0))
    st.plotly_chart(fig2, use_container_width=True)

st.markdown("---")

# ═════════════════════════════════════════════════════════════════════════════
# VISÃO 2 — CONSOLIDADO POR PARCEIRO × ITEM (todas as fases)
# ═════════════════════════════════════════════════════════════════════════════
st.markdown("### 🗂️ Visão Consolidada por Parceiro × Item (todas as fases somadas)")
st.caption("Saldo líquido independente de fase — útil quando o parceiro usou saldo de outra fase")

df_cons2 = df_base.copy()
if parceiro_sel != "Todos":
    df_cons2 = df_cons2[df_cons2["parceiro"] == parceiro_sel]
if fabr_sel != "Todos":
    df_cons2 = df_cons2[df_cons2["fabricante"] == fabr_sel]
if item_sel != "Todos":
    df_cons2 = df_cons2[df_cons2["item"] == item_sel]

df_agg2 = (
    df_cons2
    .groupby(["parceiro","item","fabricante"], dropna=False)[num_cols]
    .sum().reset_index()
)
if mostrar_negativos:
    df_agg2 = df_agg2[df_agg2["saldo_atual"] < 0]

c1b, c2b, c3b, c4b = st.columns(4)
c1b.metric("Total Recebido (consol.)", f"{int(df_agg2['total_recebido'].sum()):,}".replace(",","."))
c2b.metric("Total Baixado (consol.)",  f"{int(df_agg2['total_baixado'].sum()):,}".replace(",","."))
c3b.metric("Saldo Geral Consolidado",  f"{int(df_agg2['saldo_atual'].sum()):,}".replace(",","."))
n_neg2 = int((df_agg2["saldo_atual"] < 0).sum())
c4b.metric("Itens c/ Saldo Neg.", n_neg2,
           delta=("⚠️ Atenção" if n_neg2 > 0 else None), delta_color="inverse")

rename2 = {
    "parceiro":                    "Parceiro",
    "item":                        "Item",
    "fabricante":                  "Fabricante",
    "total_recebido":              "Recebido",
    "total_baixado":               "Baixado",
    "total_recebido_transferencia":"Transf. Recebida",
    "total_enviado_transferencia": "Transf. Enviada",
    "saldo_atual":                 "Saldo Consolidado",
}
df_show2 = df_agg2[list(rename2.keys())].rename(columns=rename2).sort_values(["Parceiro","Saldo Consolidado"])

col_g2a, col_g2b = st.columns(2)
with col_g2a:
    df_item2 = df_agg2.groupby("item")["saldo_atual"].sum().reset_index().sort_values("saldo_atual")
    fig2a = px.bar(df_item2, x="saldo_atual", y="item", orientation="h",
                   color="saldo_atual",
                   color_continuous_scale=["#d62728","#ffdd57","#2ca02c"],
                   labels={"saldo_atual":"Saldo Consolidado","item":"Item"},
                   height=380, title="Saldo Consolidado por Item")
    fig2a.update_layout(coloraxis_showscale=False, margin=dict(l=0,r=0,t=40,b=0))
    st.plotly_chart(fig2a, use_container_width=True)

with col_g2b:
    df_parc2 = df_agg2.groupby("parceiro")[["total_recebido","total_baixado"]].sum().reset_index()
    df_melt2 = df_parc2.melt(id_vars="parceiro", var_name="Tipo", value_name="Qtd")
    df_melt2["Tipo"] = df_melt2["Tipo"].map({"total_recebido":"Recebido","total_baixado":"Baixado (inst.)"})
    fig2b = px.bar(df_melt2, x="parceiro", y="Qtd", color="Tipo", barmode="group",
                   color_discrete_map={"Recebido":"#1f77b4","Baixado (inst.)":"#ff7f0e"},
                   labels={"parceiro":"Parceiro","Qtd":"Quantidade"},
                   height=380, title="Recebido vs Baixado Consolidado")
    fig2b.update_layout(margin=dict(l=0,r=0,t=40,b=0))
    st.plotly_chart(fig2b, use_container_width=True)

st.dataframe(
    df_show2.style.map(colorir, subset=["Saldo Consolidado"]),
    use_container_width=True, hide_index=True, height=420,
)
st.download_button(
    "⬇️ Exportar consolidado por item (.csv)",
    data=df_show2.to_csv(index=False).encode("utf-8"),
    file_name="saldo_consolidado_por_item.csv",
    mime="text/csv",
)

st.markdown("---")

# ═════════════════════════════════════════════════════════════════════════════
# VISÃO 3 — CONSOLIDADO POR PARCEIRO × UF (todas as fases)
# ═════════════════════════════════════════════════════════════════════════════
st.markdown("### 🗺️ Visão Consolidada por Parceiro × UF (todas as fases somadas)")
st.caption("Visão geográfica do saldo líquido por parceiro e estado")

df_cons3 = df_base.copy()
if parceiro_sel != "Todos":
    df_cons3 = df_cons3[df_cons3["parceiro"] == parceiro_sel]
if fabr_sel != "Todos":
    df_cons3 = df_cons3[df_cons3["fabricante"] == fabr_sel]
if item_sel != "Todos":
    df_cons3 = df_cons3[df_cons3["item"] == item_sel]

df_cons3["uf"] = df_cons3["parceiro"].map(parc_uf).fillna("N/D")

df_agg3 = (
    df_cons3
    .groupby(["parceiro","uf"], dropna=False)[num_cols]
    .sum().reset_index()
)
if mostrar_negativos:
    df_agg3 = df_agg3[df_agg3["saldo_atual"] < 0]

c1c, c2c, c3c, c4c = st.columns(4)
c1c.metric("Total Recebido (por UF)", f"{int(df_agg3['total_recebido'].sum()):,}".replace(",","."))
c2c.metric("Total Baixado (por UF)",  f"{int(df_agg3['total_baixado'].sum()):,}".replace(",","."))
c3c.metric("Saldo Geral (por UF)",    f"{int(df_agg3['saldo_atual'].sum()):,}".replace(",","."))
n_neg3 = int((df_agg3["saldo_atual"] < 0).sum())
c4c.metric("Parceiros c/ Saldo Neg.", n_neg3,
           delta=("⚠️ Atenção" if n_neg3 > 0 else None), delta_color="inverse")

rename3 = {
    "parceiro":                    "Parceiro",
    "uf":                          "UF",
    "total_recebido":              "Recebido",
    "total_baixado":               "Baixado",
    "total_recebido_transferencia":"Transf. Recebida",
    "total_enviado_transferencia": "Transf. Enviada",
    "saldo_atual":                 "Saldo Consolidado",
}
df_show3 = df_agg3[list(rename3.keys())].rename(columns=rename3).sort_values(["UF","Parceiro"])

col_g3a, col_g3b = st.columns(2)
with col_g3a:
    df_uf_chart = df_agg3.groupby("uf")["saldo_atual"].sum().reset_index().sort_values("saldo_atual")
    fig3a = px.bar(df_uf_chart, x="saldo_atual", y="uf", orientation="h",
                   color="saldo_atual",
                   color_continuous_scale=["#d62728","#ffdd57","#2ca02c"],
                   labels={"saldo_atual":"Saldo","uf":"UF"},
                   height=350, title="Saldo Consolidado por UF")
    fig3a.update_layout(coloraxis_showscale=False, margin=dict(l=0,r=0,t=40,b=0))
    st.plotly_chart(fig3a, use_container_width=True)

with col_g3b:
    df_parc3 = df_agg3[["parceiro","total_recebido","total_baixado"]].copy()
    df_melt3 = df_parc3.melt(id_vars="parceiro", var_name="Tipo", value_name="Qtd")
    df_melt3["Tipo"] = df_melt3["Tipo"].map({"total_recebido":"Recebido","total_baixado":"Baixado (inst.)"})
    fig3b = px.bar(df_melt3, x="parceiro", y="Qtd", color="Tipo", barmode="group",
                   color_discrete_map={"Recebido":"#1f77b4","Baixado (inst.)":"#ff7f0e"},
                   labels={"parceiro":"Parceiro","Qtd":"Quantidade"},
                   height=350, title="Recebido vs Baixado por Parceiro")
    fig3b.update_layout(margin=dict(l=0,r=0,t=40,b=0))
    st.plotly_chart(fig3b, use_container_width=True)

st.dataframe(
    df_show3.style.map(colorir, subset=["Saldo Consolidado"]),
    use_container_width=True, hide_index=True,
    height=min(60 + len(df_show3) * 35, 400),
)
st.download_button(
    "⬇️ Exportar consolidado por UF (.csv)",
    data=df_show3.to_csv(index=False).encode("utf-8"),
    file_name="saldo_consolidado_por_uf.csv",
    mime="text/csv",
)

# ── Consumo de cabo por AP ───────────────────────────────────────────────────
st.markdown("---")
st.subheader("📡 Consumo de Cabo por AP — por Parceiro e Fase")

df_cabo_ap  = carregar_consumo_cabo()
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
    df_cabo_show, use_container_width=True, hide_index=True,
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
df_neg = df_base[df_base["saldo_atual"] < 0][["parceiro","item","fase","saldo_atual"]]
if not df_neg.empty:
    st.markdown("---")
    st.warning(f"⚠️ **{len(df_neg)} linha(s) com saldo negativo detectada(s) (por fase):**")
    st.dataframe(
        df_neg.rename(columns={"parceiro":"Parceiro","item":"Item","fase":"Fase","saldo_atual":"Saldo"}),
        use_container_width=True, hide_index=True
    )

# ═════════════════════════════════════════════════════════════════════════════
# VISÃO 4 — VALORES FINANCEIROS
# ═════════════════════════════════════════════════════════════════════════════
st.markdown("---")
st.markdown("### 💰 Visão Financeira do Estoque")
st.caption("Valores em R$ calculados a partir das compras registradas (qtd recebida × valor unitário)")

df_comp, df_transf, _unit_cost = carregar_financeiro_estoque()

def fmt_brl(v):
    return f"R$ {float(v):,.0f}".replace(",","X").replace(".",",").replace("X",".")

FASES_ORDEM = ["4.1", "4.2", "4.2 ADICIONAL", "5.0"]

# ── 4 KPIs: total adquirido por fase ─────────────────────────────────────────
st.subheader("Total Adquirido por Fase")
kpi_cols = st.columns(len(FASES_ORDEM))
for col, fase in zip(kpi_cols, FASES_ORDEM):
    if df_comp.empty:
        total = 0.0
    else:
        mask = df_comp["fase"].str.upper().str.strip() == fase.upper()
        total = float(df_comp.loc[mask, "valor_comprado"].sum())
    col.metric(f"Fase {fase}", fmt_brl(total))

st.markdown("---")

# ── Tabela: valor comprado por parceiro × fase ────────────────────────────────
st.subheader("Valor Comprado por Parceiro e Fase")
if df_comp.empty:
    st.info("Nenhuma compra registrada.")
else:
    # Aplica filtro de parceiro e fase da sidebar (se selecionados)
    df_cmp_f = df_comp.copy()
    if parceiro_sel != "Todos":
        df_cmp_f = df_cmp_f[df_cmp_f["parceiro"] == parceiro_sel]
    if fase_sel != "Todas":
        df_cmp_f = df_cmp_f[df_cmp_f["fase"] == fase_sel]

    df_cmp_grp = (
        df_cmp_f.groupby(["parceiro","fase"])["valor_comprado"]
        .sum().reset_index()
        .rename(columns={"parceiro":"Parceiro","fase":"Fase","valor_comprado":"Valor Comprado"})
        .sort_values(["Fase","Valor Comprado"], ascending=[True, False])
    )
    total_comp = df_cmp_grp["Valor Comprado"].sum()
    df_cmp_show = df_cmp_grp.copy()
    df_cmp_show["Valor Comprado"] = df_cmp_show["Valor Comprado"].apply(fmt_brl)
    st.dataframe(df_cmp_show, use_container_width=True, hide_index=True,
                 height=min(60 + len(df_cmp_show)*35, 380))
    st.caption(f"**Total comprado (filtro atual): {fmt_brl(total_comp)}**")
    st.download_button("⬇️ Exportar compras (.csv)",
                       data=df_cmp_grp.to_csv(index=False).encode("utf-8"),
                       file_name="valor_comprado.csv", mime="text/csv")

st.markdown("---")

# ── Tabela: valor transferido por origem → destino ────────────────────────────
st.subheader("Valor Transferido entre Parceiros")
if df_transf.empty:
    st.info("Nenhuma transferência registrada.")
else:
    df_trf_f = df_transf.copy()
    if parceiro_sel != "Todos":
        df_trf_f = df_trf_f[
            (df_trf_f["origem"] == parceiro_sel) | (df_trf_f["destino"] == parceiro_sel)
        ]
    if fase_sel != "Todas":
        df_trf_f = df_trf_f[df_trf_f["fase"] == fase_sel]

    df_trf_grp = (
        df_trf_f.groupby(["origem","destino","fase"])["valor_transf"]
        .sum().reset_index()
        .rename(columns={"origem":"Origem","destino":"Destino",
                         "fase":"Fase","valor_transf":"Valor Transferido"})
        .sort_values("Valor Transferido", ascending=False)
    )
    total_trf = df_trf_grp["Valor Transferido"].sum()
    df_trf_show = df_trf_grp.copy()
    df_trf_show["Valor Transferido"] = df_trf_show["Valor Transferido"].apply(fmt_brl)
    st.dataframe(df_trf_show, use_container_width=True, hide_index=True,
                 height=min(60 + len(df_trf_show)*35, 320))
    st.caption(f"**Total transferido (filtro atual): {fmt_brl(total_trf)}**")
    st.download_button("⬇️ Exportar transferências (.csv)",
                       data=df_trf_grp.to_csv(index=False).encode("utf-8"),
                       file_name="valor_transferido.csv", mime="text/csv")

st.markdown("---")

# ── Tabela: valor em estoque (saldo × custo médio) ────────────────────────────
st.subheader("Valor em Estoque (Saldo Atual × Custo Médio)")
if df_comp.empty:
    st.info("Sem preços cadastrados para valorizar o estoque.")
else:
    # Custo médio por (item, fase) — chave legível para merge com vw_saldo
    df_preco = (df_comp[df_comp["valor_unitario"] > 0]
                .groupby(["item","fase"])
                .apply(lambda g: (g["valor_comprado"].sum() / g["qtd_recebida"].sum())
                                  if g["qtd_recebida"].sum() > 0 else 0.0)
                .reset_index(name="custo_medio"))

    # Aplica filtros da sidebar ao saldo base
    df_sal_f = df_base.copy()
    if parceiro_sel != "Todos":
        df_sal_f = df_sal_f[df_sal_f["parceiro"] == parceiro_sel]
    if fase_sel != "Todas":
        df_sal_f = df_sal_f[df_sal_f["fase"] == fase_sel]
    if fabr_sel != "Todos":
        df_sal_f = df_sal_f[df_sal_f["fabricante"] == fabr_sel]
    if item_sel != "Todos":
        df_sal_f = df_sal_f[df_sal_f["item"] == item_sel]

    df_val = df_sal_f.merge(df_preco, on=["item","fase"], how="left")
    df_val["custo_medio"] = df_val["custo_medio"].fillna(0)
    df_val["valor_em_estoque"] = df_val["saldo_atual"] * df_val["custo_medio"]

    df_val_show = df_val[["parceiro","item","fabricante","fase",
                           "saldo_atual","custo_medio","valor_em_estoque"]].copy()
    df_val_show = df_val_show.rename(columns={
        "parceiro":"Parceiro","item":"Item","fabricante":"Fabricante","fase":"Fase",
        "saldo_atual":"Saldo (un)","custo_medio":"Custo Médio (R$)","valor_em_estoque":"Valor em Estoque",
    }).sort_values(["Fase","Parceiro"])

    total_estoque = df_val["valor_em_estoque"].sum()

    def colorir_fin(val):
        if isinstance(val, (int,float)) and val < 0:
            return "color:#9c0006; font-weight:bold"
        return ""

    df_val_fmt = df_val_show.copy()
    df_val_fmt["Custo Médio (R$)"] = df_val_fmt["Custo Médio (R$)"].apply(
        lambda v: fmt_brl(v) if v > 0 else "—")
    df_val_fmt["Valor em Estoque"] = df_val_fmt["Valor em Estoque"].apply(fmt_brl)

    st.dataframe(df_val_fmt.style.map(colorir_fin, subset=["Saldo (un)"]),
                 use_container_width=True, hide_index=True,
                 height=min(60 + len(df_val_fmt)*35, 420))
    st.caption(f"**Valor total em estoque (filtro atual): {fmt_brl(total_estoque)}**")
    st.download_button("⬇️ Exportar estoque valorizado (.csv)",
                       data=df_val_show.to_csv(index=False).encode("utf-8"),
                       file_name="estoque_valorizado.csv", mime="text/csv")
