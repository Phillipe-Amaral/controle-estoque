import streamlit as st
from supabase import create_client
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import date, datetime
import io, base64

st.set_page_config(page_title="Financeiro | IUH Digital", page_icon="📊", layout="wide")

# ── Tema IUH ──────────────────────────────────────────────────────────────────
IUH_TEAL    = "#0C6679"   # teal escuro (letras iuh)
IUH_ACCENT  = "#2EDBA0"   # verde menta (exclamação)
IUH_DARK    = "#0a4a5a"
IUH_DARKER  = "#073a48"

IUH_CSS = f"""
<style>
/* ── Base ── */
html, body, [data-testid="stAppViewContainer"] {{
    background: #f0f4f8;
    font-family: 'Segoe UI', Arial, sans-serif;
}}
/* accent verde menta nos destaques */
[data-testid="stMetric"] {{ border-left-color: {IUH_ACCENT}; }}
.main .block-container {{
    padding-top: 1.2rem;
    padding-bottom: 2rem;
    max-width: 1400px;
}}

/* ── Sidebar ── */
[data-testid="stSidebar"] > div:first-child {{
    background: linear-gradient(180deg, #0a3d4a 0%, #062e39 100%);
    padding-top: 0;
}}
[data-testid="stSidebar"] * {{ color: #cbd5e0 !important; }}
[data-testid="stSidebar"] h1,
[data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3 {{ color: #ffffff !important; }}
[data-testid="stSidebar"] label {{
    color: #94a3b8 !important;
    font-size: 0.73rem !important;
    font-weight: 700 !important;
    text-transform: uppercase;
    letter-spacing: 0.06em;
}}
[data-testid="stSidebar"] hr {{ border-color: #2d3f60 !important; }}
[data-testid="stSidebar"] .stButton > button {{
    background: {IUH_TEAL} !important;
    color: white !important;
    border: none !important;
    border-radius: 6px !important;
    font-weight: 600 !important;
    width: 100%;
}}
[data-testid="stSidebar"] .stButton > button:hover {{
    background: #0d9db0 !important;
}}

/* ── KPI Metric cards ── */
[data-testid="stMetric"] {{
    background: #ffffff;
    border-radius: 10px;
    padding: 1rem 1.1rem 0.9rem;
    border-left: 4px solid {IUH_TEAL};
    box-shadow: 0 1px 6px rgba(0,0,0,0.07);
    margin-bottom: 0.4rem;
}}
[data-testid="stMetricLabel"] > div {{
    font-size: 0.68rem !important;
    font-weight: 700 !important;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: #64748b !important;
}}
[data-testid="stMetricValue"] > div {{
    font-size: 1.45rem !important;
    font-weight: 800 !important;
    color: {IUH_DARK} !important;
}}
[data-testid="stMetricDelta"] > div {{
    font-size: 0.8rem !important;
    font-weight: 600 !important;
}}

/* ── Tabs ── */
[data-testid="stTabs"] [data-baseweb="tab-list"] {{
    background: white;
    border-radius: 8px 8px 0 0;
    padding: 0 0.5rem;
    box-shadow: 0 1px 4px rgba(0,0,0,0.06);
    gap: 0;
}}
[data-testid="stTabs"] [data-baseweb="tab"] {{
    font-weight: 600;
    font-size: 0.85rem;
    color: #64748b;
    padding: 0.75rem 1.1rem;
    border-bottom: 3px solid transparent;
}}
[data-testid="stTabs"] [aria-selected="true"] {{
    color: {IUH_TEAL} !important;
    border-bottom: 3px solid {IUH_TEAL} !important;
    background: transparent !important;
}}

/* ── Subheadings ── */
h2, h3 {{
    color: {IUH_DARK} !important;
    font-weight: 700 !important;
}}

/* ── Cards de seção ── */
[data-testid="stHorizontalBlock"] > div {{
    gap: 0.6rem;
}}

/* ── Multiselect tag color ── */
[data-baseweb="tag"] {{
    background-color: {IUH_TEAL} !important;
}}

/* ── Download / primary buttons ── */
.stDownloadButton > button,
.stButton [kind="primary"] {{
    background-color: {IUH_TEAL} !important;
    border: none !important;
    color: white !important;
    font-weight: 700 !important;
    border-radius: 7px !important;
}}

/* ── Divisor ── */
hr {{ border-color: #e2e8f0 !important; margin: 1.2rem 0 !important; }}

/* ── Página header ── */
.iuh-header {{
    background: white;
    border-radius: 12px;
    padding: 1.2rem 1.6rem;
    margin-bottom: 1.2rem;
    box-shadow: 0 1px 6px rgba(0,0,0,0.07);
    border-left: 5px solid {IUH_ACCENT};
    display: flex;
    align-items: center;
    gap: 1.2rem;
}}
.iuh-header-title {{
    font-size: 1.5rem;
    font-weight: 800;
    color: {IUH_DARK};
    margin: 0;
    line-height: 1.2;
}}
.iuh-header-sub {{
    font-size: 0.82rem;
    color: #64748b;
    margin: 0.15rem 0 0;
}}

/* ── Sidebar logo box ── */
.iuh-logo-box {{
    background: linear-gradient(135deg, {IUH_TEAL}22 0%, transparent 100%);
    border-bottom: 1px solid #2d3f60;
    padding: 1.1rem 1.2rem 0.9rem;
    margin-bottom: 0.5rem;
}}
.iuh-logo-text {{
    font-size: 2rem;
    font-weight: 900;
    color: {IUH_TEAL} !important;
    letter-spacing: -2px;
    line-height: 1;
}}
.iuh-logo-sub {{
    font-size: 0.65rem;
    letter-spacing: 0.2em;
    color: #94a3b8 !important;
    font-weight: 600;
    text-transform: uppercase;
    margin-top: 2px;
}}
</style>
"""
st.markdown(IUH_CSS, unsafe_allow_html=True)

SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]

@st.cache_resource
def get_client():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

sb = get_client()

@st.cache_data(ttl=300)
def carregar_financeiro():
    rows = []
    page, size = 0, 1000
    while True:
        r = sb.table("financeiro_inep").select("*").range(page*size, (page+1)*size-1).execute()
        if not r.data:
            break
        rows.extend(r.data)
        page += 1
    df = pd.DataFrame(rows)
    for c in ['data_inst_ri','data_manut_ri','data_inst_re','data_rdo']:
        if c in df.columns:
            df[c] = pd.to_datetime(df[c], errors='coerce')
    num_cols = [c for c in df.columns if c not in
                ['inep','escola','uf','municipio','fase','lote','parceiro_ri',
                 'responsavel_re','kit_previsto','kit_real','status_parcial','status_rdo','updated_at']]
    for c in num_cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0)
    return df

TODAY = date.today()

# ── Carrega dados ─────────────────────────────────────────────────────────────
df_all = carregar_financeiro()

if df_all.empty:
    st.error("⚠️ Tabela financeiro_inep vazia. Rode construir_modelo_financeiro.py primeiro.")
    st.stop()

# ── Helpers ───────────────────────────────────────────────────────────────────
def fmt_brl(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "R$ —"
    return f"R$ {float(v):,.0f}".replace(",", "X").replace(".", ",").replace("X", ".")

def apply_filters(df, estados=None, fases=None, inep=None, responsavel=None,
                  data_inst_ri=None, data_inst_re=None, data_rdo=None):
    d = df.copy()
    if estados:
        d = d[d['uf'].isin(estados)]
    if fases:
        d = d[d['fase'].isin(fases)]
    if inep:
        d = d[d['inep'].str.contains(inep, na=False)]
    if responsavel:
        d = d[d['responsavel_re'].isin(responsavel)]
    if data_inst_ri:
        col = pd.to_datetime(d['data_inst_ri'], errors='coerce')
        mask = col.notna()
        if mask.any():
            d = d[~mask | ((col.dt.date >= data_inst_ri[0]) & (col.dt.date <= data_inst_ri[1]))]
    if data_inst_re:
        col = pd.to_datetime(d['data_inst_re'], errors='coerce')
        mask = col.notna()
        if mask.any():
            d = d[~mask | ((col.dt.date >= data_inst_re[0]) & (col.dt.date <= data_inst_re[1]))]
    if data_rdo:
        col = pd.to_datetime(d['data_rdo'], errors='coerce')
        mask = col.notna()
        if mask.any():
            d = d[~mask | ((col.dt.date >= data_rdo[0]) & (col.dt.date <= data_rdo[1]))]
    return d

def to_excel(df_export):
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine='openpyxl') as writer:
        df_export.to_excel(writer, index=False, sheet_name='Financeiro')
    return buf.getvalue()

# ── Sidebar ───────────────────────────────────────────────────────────────────
# Logo IUH como base64 (compatível com Streamlit Cloud)
import pathlib
_logo_path = pathlib.Path(__file__).parent.parent / "assets" / "logo_iuh.png"
if _logo_path.exists():
    _logo_b64 = base64.b64encode(_logo_path.read_bytes()).decode()
    st.sidebar.markdown(f"""
<div class="iuh-logo-box" style="text-align:center">
  <img src="data:image/png;base64,{_logo_b64}"
       style="width:140px; margin:0 auto; display:block; filter:brightness(0) invert(1);" />
  <div class="iuh-logo-sub" style="margin-top:6px;">Painel Financeiro</div>
</div>
""", unsafe_allow_html=True)
else:
    st.sidebar.markdown("""
<div class="iuh-logo-box">
  <div class="iuh-logo-text">iuh!</div>
  <div class="iuh-logo-sub">Painel Financeiro</div>
</div>
""", unsafe_allow_html=True)
st.sidebar.markdown("### 🔍 Filtros")
STATUS_RDO_ORDEM = [
    'RDO Aprovada','Em Aprovação EACE','Em Aprovação IUH - Subir RDO',
    'Em Execução Técnico','RDO Reprovada','Sem RDO','Cancelado',
]
estados_list  = sorted(df_all['uf'].dropna().unique().tolist())
fases_list    = sorted(df_all['fase'].dropna().unique().tolist())
resp_list     = sorted(df_all['responsavel_re'].dropna().unique().tolist())
status_rdo_list = [s for s in STATUS_RDO_ORDEM
                   if s in df_all.get('status_rdo', pd.Series(dtype=str)).dropna().unique()]

sel_estados   = st.sidebar.multiselect("Estado (UF)", estados_list)
sel_fases     = st.sidebar.multiselect("Fase", fases_list)
sel_resp      = st.sidebar.multiselect("Responsável RE", resp_list)
sel_status_rdo = st.sidebar.multiselect("Status RDO (ANIEL)", status_rdo_list)
sel_inep      = st.sidebar.text_input("Buscar INEP")

st.sidebar.markdown("---")
st.sidebar.caption(f"Base: {len(df_all):,} escolas | Atualizado: {TODAY}")

if st.sidebar.button("🔄 Atualizar dados"):
    st.cache_data.clear()
    st.rerun()

df_f = apply_filters(df_all, estados=sel_estados or None, fases=sel_fases or None,
                     inep=sel_inep or None, responsavel=sel_resp or None)
if sel_status_rdo and 'status_rdo' in df_f.columns:
    df_f = df_f[df_f['status_rdo'].isin(sel_status_rdo)]

# ── Título ────────────────────────────────────────────────────────────────────
st.markdown(f"""
<div class="iuh-header">
  <div>
    <p class="iuh-header-title">📊 Painel Financeiro — Custos e Receitas</p>
    <p class="iuh-header-sub">
        {len(df_f):,} escolas selecionadas &nbsp;·&nbsp; Atualizado em {TODAY.strftime('%d/%m/%Y')}
    </p>
  </div>
</div>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📊 KPIs Gerais",
    "🔌 Rede Externa (RE)",
    "📡 Rede Interna (RI)",
    "📋 Relatório por INEP",
    "⬇️ Exportar Excel",
])

# ══════════════════════════════════════════════════════════════════════════════
# ABA 1 — KPIs GERAIS
# ══════════════════════════════════════════════════════════════════════════════
with tab1:
    st.subheader("Visão Consolidada — Custo Real × Receita Real")

    col1, col2, col3, col4 = st.columns(4)
    rec_parc  = df_f['receita_parcial'].sum()
    cus_parc  = df_f['custo_parcial'].sum()
    marg_parc = rec_parc - cus_parc
    rec_24m   = df_f['receita_24m_total_real'].sum()
    cus_24m   = df_f['custo_24m_total_real'].sum()
    marg_24m  = rec_24m - cus_24m

    col1.metric("Receita Parcial Gerada",   fmt_brl(rec_parc))
    col2.metric("Custo Parcial Gerado",     fmt_brl(cus_parc))
    col3.metric("Margem Parcial",           fmt_brl(marg_parc),
                delta=f"{marg_parc/rec_parc*100:.1f}%" if rec_parc else None,
                delta_color="normal")
    col4.metric("Receita 24M Real Projetada", fmt_brl(rec_24m))

    col5, col6, col7, col8 = st.columns(4)
    col5.metric("Custo 24M Real Projetado", fmt_brl(cus_24m))
    col6.metric("Margem 24M Real",          fmt_brl(marg_24m),
                delta=f"{marg_24m/rec_24m*100:.1f}%" if rec_24m else None,
                delta_color="normal")
    n_lucro   = (df_f['margem_parcial'] > 0).sum()
    n_prej    = (df_f['margem_parcial'] < 0).sum()
    col7.metric("INEPs em LUCRO (parcial)",   n_lucro)
    col8.metric("INEPs em PREJUÍZO (parcial)", n_prej,
                delta_color="inverse" if n_prej > 0 else "off")

    st.markdown("---")

    # KPI por tipo de receita/custo
    st.subheader("KPI por Tipo de Receita × Custo (24M Real)")
    k1, k2, k3 = st.columns(3)

    # Equipamentos RI
    rec_eq  = df_f['rec_equip_ri_real'].sum()
    cus_eq  = df_f['custo_equip_cmv'].sum()
    marg_eq = rec_eq - cus_eq
    with k1:
        st.markdown("**📦 Equipamentos RI**")
        st.metric("Receita Equip RI",  fmt_brl(rec_eq))
        st.metric("Custo CMV",         fmt_brl(cus_eq))
        st.metric("Margem Equip",      fmt_brl(marg_eq),
                  delta=f"{marg_eq/rec_eq*100:.1f}%" if rec_eq else None, delta_color="normal")

    # Serviço + Manutenção RI
    rec_sv  = df_f['rec_serv_ri_real'].sum() + df_f['rec_manut_24m_ri'].sum()
    cus_sv  = df_f['custo_serv_ri'].sum()
    marg_sv = rec_sv - cus_sv
    with k2:
        st.markdown("**🔧 Serviço + Manutenção RI**")
        st.metric("Receita Serv+Manut RI", fmt_brl(rec_sv))
        st.metric("Custo Serv RI",         fmt_brl(cus_sv))
        st.metric("Margem Serv RI",        fmt_brl(marg_sv),
                  delta=f"{marg_sv/rec_sv*100:.1f}%" if rec_sv else None, delta_color="normal")

    # Rede Externa RE
    rec_re  = df_f['rec_inst_re_prev'].sum() + df_f['rec_mens_re_24m'].sum()
    cus_re  = df_f['custo_24m_re_real'].where(df_f['custo_24m_re_real'] > 0,
                                               df_f['custo_24m_re_orc']).sum()
    marg_re = rec_re - cus_re
    with k3:
        st.markdown("**🌐 Rede Externa RE**")
        st.metric("Receita RE 24M",  fmt_brl(rec_re))
        st.metric("Custo RE 24M",    fmt_brl(cus_re))
        st.metric("Margem RE",       fmt_brl(marg_re),
                  delta=f"{marg_re/rec_re*100:.1f}%" if rec_re else None, delta_color="normal")

    st.markdown("---")

    # Custo real × Receita real RI por fase
    st.subheader("Custo Real × Receita Real RI por Fase")
    df_fase = df_f.groupby('fase').agg(
        Receita_RI=('receita_24m_total_real','sum'),
        Custo_RI=('custo_24m_total_real','sum'),
    ).reset_index()
    df_fase['Margem'] = df_fase['Receita_RI'] - df_fase['Custo_RI']
    df_fase_m = df_fase.melt(id_vars='fase', value_vars=['Receita_RI','Custo_RI','Margem'],
                              var_name='Métrica', value_name='Valor (R$)')
    fig_fase = px.bar(df_fase_m, x='fase', y='Valor (R$)', color='Métrica', barmode='group',
                      color_discrete_map={'Receita_RI':'#2ca02c','Custo_RI':'#d62728','Margem':'#1f77b4'},
                      height=380)
    fig_fase.update_layout(margin=dict(l=0,r=0,t=20,b=0))
    st.plotly_chart(fig_fase, use_container_width=True)

    st.markdown("---")

    # Receita e custo médio por AP instalado
    st.subheader("Receita e Custo Médio por AP Instalado")
    c_fa, c_fb, c_fc = st.columns(3)
    with c_fa:
        fa_fase = st.multiselect("Fase", fases_list, key="ap_fase")
    with c_fb:
        fa_uf   = st.multiselect("Estado", estados_list, key="ap_uf")
    with c_fc:
        fa_data = st.date_input("Data Instalação RI (de/até)",
                                value=(date(2024,1,1), TODAY), key="ap_data")

    fa_data_safe = fa_data if (isinstance(fa_data, (list, tuple)) and len(fa_data) == 2) else None
    df_ap = apply_filters(df_f,
                          fases=fa_fase or None, estados=fa_uf or None,
                          data_inst_ri=fa_data_safe)
    df_ap = df_ap[df_ap['aps_ad_impl'] > 0]
    if not df_ap.empty:
        df_ap_g = df_ap.groupby('fase').apply(lambda x: pd.Series({
            'Receita Média/AP':  (x['receita_24m_total_real'] / x['aps_ad_impl']).mean(),
            'Custo Médio/AP':    (x['custo_24m_total_real']   / x['aps_ad_impl']).mean(),
        })).reset_index()
        fig_ap = px.bar(df_ap_g.melt('fase'), x='fase', y='value', color='variable',
                        barmode='group', labels={'value':'R$ por AP','variable':''},
                        color_discrete_map={'Receita Média/AP':'#2ca02c','Custo Médio/AP':'#d62728'},
                        height=350)
        st.plotly_chart(fig_ap, use_container_width=True)
    else:
        st.info("Nenhum registro com APs adicionais para os filtros selecionados.")

    st.markdown("---")

    # Pizza LUCRO × PREJUÍZO
    st.subheader("% INEPs com Receita Positiva × Negativa (parcial)")
    c_pza, c_pzb = st.columns(2)
    with c_pza:
        pz_fase = st.multiselect("Fase", fases_list, key="pz_fase")
    with c_pzb:
        pz_uf   = st.multiselect("Estado", estados_list, key="pz_uf")

    df_pz = apply_filters(df_f, fases=pz_fase or None, estados=pz_uf or None)
    df_pz = df_pz[df_pz['status_parcial'].notna()]
    if not df_pz.empty:
        counts = df_pz['status_parcial'].value_counts().reset_index()
        counts.columns = ['Status', 'Qtd']
        colors = {'LUCRO':'#2ca02c','PREJUÍZO':'#d62728','NEUTRO':'#aec7e8','PENDENTE':'#ffb347'}
        fig_pz = px.pie(counts, names='Status', values='Qtd',
                        color='Status', color_discrete_map=colors, height=380,
                        title=f'{len(df_pz):,} INEPs')
        fig_pz.update_traces(textposition='inside', textinfo='percent+label+value')
        st.plotly_chart(fig_pz, use_container_width=True)

# ══════════════════════════════════════════════════════════════════════════════
# ABA 2 — REDE EXTERNA
# ══════════════════════════════════════════════════════════════════════════════
with tab2:
    st.subheader("KPI: Custo Orçado RE × Custo Real RE (24M)")

    cre1, cre2, cre3 = st.columns(3)
    with cre1:
        re_uf   = st.multiselect("Estado", estados_list, key="re_uf")
    with cre2:
        re_fase = st.multiselect("Fase", fases_list, key="re_fase")
    with cre3:
        re_resp = st.multiselect("Responsável", resp_list, key="re_resp")
    re_inep = st.text_input("Buscar INEP", key="re_inep")

    df_re = apply_filters(df_f, estados=re_uf or None, fases=re_fase or None,
                          inep=re_inep or None, responsavel=re_resp or None)

    orc24  = df_re['custo_24m_re_orc'].sum()
    real24 = df_re['custo_24m_re_real'].sum()
    delta  = real24 - orc24
    r1, r2, r3, r4 = st.columns(4)
    r1.metric("Custo Orçado 24M RE",  fmt_brl(orc24))
    r2.metric("Custo Real 24M RE",    fmt_brl(real24))
    r3.metric("Delta (Real - Orçado)",fmt_brl(delta),
              delta_color="inverse" if delta > 0 else "normal")
    r4.metric("Escolas com RE real",  int((df_re['custo_24m_re_real'] > 0).sum()))

    # Bar por UF
    df_re_uf = df_re.groupby('uf').agg(
        Orçado_24M=('custo_24m_re_orc','sum'),
        Real_24M=('custo_24m_re_real','sum'),
    ).reset_index().sort_values('Real_24M', ascending=False).head(20)
    fig_re = px.bar(df_re_uf.melt('uf'), x='uf', y='value', color='variable',
                    barmode='group', labels={'value':'R$ (24M)','variable':''},
                    color_discrete_map={'Orçado_24M':'#1f77b4','Real_24M':'#ff7f0e'},
                    height=380, title="Custo RE 24M por UF (top 20)")
    st.plotly_chart(fig_re, use_container_width=True)

    st.markdown("---")
    st.subheader("KPI: Custo Real RE × Receita Projetada RE")

    rec_re_proj = df_re['rec_mens_re_24m'].sum() + df_re['rec_inst_re_prev'].sum()
    cus_re_real = df_re['custo_24m_re_real'].sum()
    margem_re   = rec_re_proj - cus_re_real

    r5, r6, r7 = st.columns(3)
    r5.metric("Receita Projetada RE 24M",  fmt_brl(rec_re_proj))
    r6.metric("Custo Real RE 24M",         fmt_brl(cus_re_real))
    r7.metric("Margem RE",                 fmt_brl(margem_re),
              delta=f"{margem_re/rec_re_proj*100:.1f}%" if rec_re_proj else None,
              delta_color="normal")

    # Scatter por UF
    df_sc = df_re.groupby('uf').agg(
        Receita_RE=('rec_mens_re_24m','sum'),
        Custo_RE=('custo_24m_re_real','sum'),
        Escolas=('inep','count'),
    ).reset_index()
    fig_sc = px.scatter(df_sc, x='Custo_RE', y='Receita_RE', size='Escolas',
                        color='uf', hover_name='uf', height=380,
                        labels={'Custo_RE':'Custo Real RE 24M (R$)','Receita_RE':'Receita Proj RE 24M (R$)'},
                        title="Custo vs Receita RE por UF")
    # Linha de equilíbrio
    mx = max(df_sc[['Custo_RE','Receita_RE']].max().max(), 1)
    fig_sc.add_shape(type='line', x0=0, y0=0, x1=mx, y1=mx,
                     line=dict(dash='dash', color='gray'))
    st.plotly_chart(fig_sc, use_container_width=True)

# ══════════════════════════════════════════════════════════════════════════════
# ABA 3 — REDE INTERNA
# ══════════════════════════════════════════════════════════════════════════════
with tab3:
    st.subheader("KPI: Custo Real × Receita Real Consolidada")

    cri1, cri2, cri3 = st.columns(3)
    with cri1:
        ri_fase = st.multiselect("Fase", fases_list, key="ri_fase")
    with cri2:
        ri_uf   = st.multiselect("Estado", estados_list, key="ri_uf")
    with cri3:
        ri_dri  = st.date_input("Inst RI (de/até)", value=(date(2024,1,1), TODAY), key="ri_dri")

    cri4, cri5 = st.columns(2)
    with cri4:
        ri_dre  = st.date_input("Inst RE (de/até)", value=(date(2024,1,1), TODAY), key="ri_dre")
    with cri5:
        ri_drdo = st.date_input("Aprovação RDO (de/até)", value=(date(2024,1,1), TODAY), key="ri_drdo")

    def safe_date(v):
        return v if (isinstance(v, (list, tuple)) and len(v) == 2) else None
    df_ri = apply_filters(df_f, fases=ri_fase or None, estados=ri_uf or None,
                          data_inst_ri=safe_date(ri_dri),
                          data_inst_re=safe_date(ri_dre),
                          data_rdo=safe_date(ri_drdo))

    c1, c2, c3, c4 = st.columns(4)
    rec_tot  = df_ri['receita_24m_total_real'].sum()
    cus_tot  = df_ri['custo_24m_total_real'].sum()
    marg_tot = rec_tot - cus_tot
    c1.metric("Receita 24M Real",   fmt_brl(rec_tot))
    c2.metric("Custo 24M Real",     fmt_brl(cus_tot))
    c3.metric("Margem 24M Real",    fmt_brl(marg_tot),
              delta=f"{marg_tot/rec_tot*100:.1f}%" if rec_tot else None,
              delta_color="normal")
    c4.metric("Escolas filtradas",  len(df_ri))

    # Waterfall por parceiro RI
    st.markdown("---")
    st.subheader("Receita Real × Custo Real por Parceiro RI")
    df_parc = df_ri.groupby('parceiro_ri').agg(
        Receita_24M=('receita_24m_total_real','sum'),
        Custo_24M=('custo_24m_total_real','sum'),
        Escolas=('inep','count'),
    ).reset_index().sort_values('Receita_24M', ascending=False)
    df_parc['Margem'] = df_parc['Receita_24M'] - df_parc['Custo_24M']
    df_parc_m = df_parc.melt('parceiro_ri', value_vars=['Receita_24M','Custo_24M','Margem'],
                               var_name='Tipo', value_name='Valor')
    fig_parc = px.bar(df_parc_m, x='parceiro_ri', y='Valor', color='Tipo', barmode='group',
                      color_discrete_map={'Receita_24M':'#2ca02c','Custo_24M':'#d62728','Margem':'#1f77b4'},
                      height=420, labels={'parceiro_ri':'Parceiro RI','Valor':'R$'})
    fig_parc.update_xaxes(tickangle=45)
    fig_parc.update_layout(margin=dict(b=120))
    st.plotly_chart(fig_parc, use_container_width=True)

# ══════════════════════════════════════════════════════════════════════════════
# ABA 4 — RELATÓRIO POR INEP
# ══════════════════════════════════════════════════════════════════════════════
with tab4:
    st.subheader("Relatório Detalhado por INEP")
    st.caption("Todas as colunas de custo e receita — previsto 24M e parcial gerado até hoje")

    col_display = {
        'inep':'INEP','escola':'Escola','uf':'UF','fase':'Fase',
        'parceiro_ri':'Parceiro RI','responsavel_re':'Responsável RE',
        'kit_previsto':'Kit Prev','kit_real':'Kit Real','aps_ad_impl':'APs Ad.',
        'data_inst_ri':'Inst RI','data_inst_re':'Inst RE','data_rdo':'RDO',
        # Receita prevista RI
        'rec_equip_ri_prev':'Rec Equip RI Prev','rec_serv_ri_prev':'Rec Serv RI Prev',
        'rec_manut_24m_ri':'Manut 24M RI',
        # Receita prevista RE
        'rec_inst_re_prev':'Inst RE Prev','rec_mens_re_24m':'Mensalidade RE 24M',
        # Receita real
        'rec_equip_ri_real':'Rec Equip RI Real','rec_serv_ri_real':'Rec Serv RI Real',
        # Custos
        'custo_serv_ri':'Custo Serv RI','custo_equip_cmv':'CMV RI',
        'custo_24m_re_orc':'Custo RE 24M Orç','custo_24m_re_real':'Custo RE 24M Real',
        # Parcial
        'receita_parcial':'Rec Parcial','custo_parcial':'Custo Parcial',
        'margem_parcial':'Margem Parcial','status_parcial':'Status',
        # 24M
        'receita_24m_total_real':'Rec 24M Real','custo_24m_total_real':'Custo 24M Real',
        'margem_24m_real':'Margem 24M Real',
    }
    existing = {k:v for k,v in col_display.items() if k in df_f.columns}
    df_show = df_f[list(existing.keys())].rename(columns=existing).copy()

    # Format date columns
    for dc in ['Inst RI','Inst RE','RDO']:
        if dc in df_show.columns:
            col_dt = pd.to_datetime(df_show[dc], errors='coerce')
            df_show[dc] = col_dt.dt.strftime('%d/%m/%Y').where(col_dt.notna(), '')

    def colorir(val):
        if isinstance(val, str):
            if val == 'LUCRO':    return 'background-color:#c6efce; color:#276221'
            if val == 'PREJUÍZO': return 'background-color:#ffc7ce; color:#9c0006'
            if val == 'PENDENTE': return 'background-color:#fff2cc; color:#7d6608'
        if isinstance(val, (int, float)):
            if val < 0: return 'color:#9c0006; font-weight:bold'
        return ''

    st.dataframe(
        df_show.style.map(colorir),
        use_container_width=True, hide_index=True, height=520,
    )
    st.caption(f"{len(df_show):,} registros")

# ══════════════════════════════════════════════════════════════════════════════
# ABA 5 — EXPORTAR
# ══════════════════════════════════════════════════════════════════════════════
with tab5:
    st.subheader("⬇️ Exportar dados filtrados para Excel")

    opcao = st.radio("Dados a exportar:",
                     ["Relatório completo (todos os campos)",
                      "Resumo financeiro (custos e receitas agregados)"])

    if opcao.startswith("Resumo"):
        df_exp = df_f.groupby(['fase','uf','parceiro_ri']).agg(
            Escolas=('inep','count'),
            Kit_Real_Total=('aps_ad_impl','sum'),
            Receita_24M_Prevista=('receita_24m_total_prev','sum'),
            Receita_24M_Real=('receita_24m_total_real','sum'),
            Custo_24M_Previsto=('custo_24m_total_prev','sum'),
            Custo_24M_Real=('custo_24m_total_real','sum'),
            Margem_24M_Real=('margem_24m_real','sum'),
            Receita_Parcial=('receita_parcial','sum'),
            Custo_Parcial=('custo_parcial','sum'),
            Margem_Parcial=('margem_parcial','sum'),
        ).reset_index()
    else:
        df_exp = df_f.copy()
        for dc in ['data_inst_ri','data_manut_ri','data_inst_re','data_rdo']:
            if dc in df_exp.columns:
                col_dt = pd.to_datetime(df_exp[dc], errors='coerce')
                df_exp[dc] = col_dt.dt.strftime('%d/%m/%Y').where(col_dt.notna(), '')

    xls = to_excel(df_exp)
    st.download_button(
        label="⬇️ Baixar Excel",
        data=xls,
        file_name=f"financeiro_{TODAY}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
        type="primary",
    )
    st.dataframe(df_exp.head(20), use_container_width=True, hide_index=True)
    st.caption(f"{len(df_exp):,} registros para exportação")
