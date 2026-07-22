import sys, pathlib, re
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from supabase import create_client
from utils.tema_iuh import aplicar_tema, sidebar_logo, page_header

st.set_page_config(page_title="Previsão de Estoque | IUH Digital", page_icon="📦", layout="wide")
aplicar_tema()

SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]

BASE = r"C:\Users\Usuário\OneDrive - IUH DIGITAL LTDA\Corporativo - 6.01 Compras_e_Contratações"
CIRC_FILE  = r"C:\Users\Usuário\Downloads\circuitos Rede Interna 22-07.xlsx"
EXEC_FILE  = BASE + r"\RFP´s e Contratos\Execução por localidade Satélite e 4.2.xlsx"
TOPO_FILE  = BASE + r"\Rede Interna\Pedidos\TOPOLOGIA POR FASE E FABRICANTE.xlsx"

# ── Status ────────────────────────────────────────────────────────────────────
STATUS_INSTALADO  = {'Ativo', 'Instalado'}
STATUS_A_INSTALAR = {'Circuito com Contrato Fechado', 'Agendado',
                     'Implantação em andamento', 'Instalado com Pendência'}
STATUS_SUSPENSO   = {'Em Reforma', 'Cancelado', 'Suspenso'}

# ── Helpers ───────────────────────────────────────────────────────────────────
def _norm_fase(f):
    f = str(f).strip().upper()
    if 'ADICIONAL' in f or 'ADICION' in f: return '4.2 ADICIONAL'
    if '5.0' in f or 'FASE 2' in f or 'FASE 3' in f or 'FASE 4' in f: return '5.0'
    if '4.2' in f: return '4.2'
    if '4.1' in f or 'FASE 1' in f: return '4.1'
    if 'SATÉLITE' in f or 'SATELITE' in f: return 'SATÉLITE'
    return f

def _parse_kit_num(s):
    """Extrai o número do kit de strings como 'INTELBRAS KIT 3' ou 'TP Link KIT 08 - Fase 2'"""
    if pd.isna(s) or str(s).strip() in ('', 'nan', 'None'):
        return None
    m = re.search(r'KIT\s+0*(\d+)', str(s), re.IGNORECASE)
    return int(m.group(1)) if m else None

def _parse_fab(s):
    s = str(s).upper()
    if 'INTELBRAS' in s: return 'INTELBRAS'
    if 'TP-LINK' in s or 'TP LINK' in s or 'TPLINK' in s: return 'TP-LINK'
    if 'DATACOM' in s: return 'DATACOM'
    if 'HUAWEI' in s: return 'HUAWEI'
    return None

# ─────────────────────────────────────────────────────────────────────────────
# CARGA DE DADOS (cache 10 min)
# ─────────────────────────────────────────────────────────────────────────────
@st.cache_data(ttl=600)
def load_saldo():
    sb = create_client(SUPABASE_URL, SUPABASE_KEY)
    rows = sb.table("vw_saldo").select("*").execute().data
    df = pd.DataFrame(rows)
    for c in ['total_recebido','total_baixado','total_recebido_transferencia',
              'total_enviado_transferencia','saldo_atual']:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0)
    return df

@st.cache_data(ttl=600)
def load_circuitos():
    df = pd.read_excel(CIRC_FILE, sheet_name='Circuitos', dtype=str, header=0)
    df.columns = df.columns.str.strip()
    df['inep'] = df['Código INEP'].astype(str).str.strip().str.replace('.0','',regex=False)
    df['status'] = df['Status Circuito'].astype(str).str.strip()
    df['fase_raw'] = df.get('Fase', df.get('Projeto', pd.Series(dtype=str))).fillna('')
    df['fase'] = df['fase_raw'].apply(_norm_fase)
    df['uf'] = df.get('UF', pd.Series(dtype=str)).astype(str).str.strip()
    df['parceiro'] = df.get('Fornecedor (Fantasia)', df.get('Fornecedor',
                     pd.Series(dtype=str))).astype(str).str.strip()
    df['kit_impl_str'] = df.get('KIT Implementado', pd.Series(dtype=str)).fillna('')
    df['kit_plan_str'] = df.get('KIT Planejado', df.get('KIT A SER INSTALADO RI',
                         pd.Series(dtype=str))).fillna('')
    df['kit_impl'] = df['kit_impl_str'].apply(_parse_kit_num)
    df['kit_plan'] = df['kit_plan_str'].apply(_parse_kit_num)
    df['aps_plan'] = pd.to_numeric(df.get('APs Ad. Planejados',
                     df.get('AP ADICIONAL RI', pd.Series(dtype=str))), errors='coerce').fillna(0)
    df['aps_impl'] = pd.to_numeric(df.get('APs Ad. Implementados',
                     pd.Series(dtype=str)), errors='coerce').fillna(0)
    df['fab'] = df['kit_impl_str'].apply(_parse_fab).fillna(df['kit_plan_str'].apply(_parse_fab))
    df = df[df['inep'].str.match(r'^\d{7,8}$', na=False)].copy()
    return df

@st.cache_data(ttl=3600)
def load_topologia():
    df = pd.read_excel(TOPO_FILE, sheet_name='Planilha1', header=0)
    df.columns = df.columns.str.strip()
    df['fase'] = df['FASE'].astype(str).str.strip().apply(_norm_fase)
    df['fab']  = df['FORNECEDOR/FABRICANTE'].astype(str).str.strip().str.upper()
    df['uf']   = df['UF'].astype(str).str.strip()
    df['kit']  = pd.to_numeric(df['KIT'], errors='coerce')
    df['item'] = df['DESCRICAO'].astype(str).str.strip()
    df['funcao'] = df['FUNÇÃO'].astype(str).str.strip()
    df['qtd']  = pd.to_numeric(df['QTD'], errors='coerce').fillna(0)
    return df[['fase','fab','uf','kit','item','funcao','qtd']].copy()

@st.cache_data(ttl=3600)
def load_exec_divisao():
    """Divisão por Parceiros: INEP → Fornecedor, Kit planejado, AP adicional"""
    df = pd.read_excel(EXEC_FILE, sheet_name='Divisão por Parceiros', dtype=str, header=0)
    df.columns = df.columns.str.strip()
    df['inep'] = df['Código INEP'].astype(str).str.strip().str.replace('.0','',regex=False)
    df['parceiro'] = df.get('Fornecedor', pd.Series(dtype=str)).astype(str).str.strip()
    df['fase'] = df.get('Lote', df.get('Fase', pd.Series(dtype=str))).apply(_norm_fase)
    df['uf']   = df.get('UF', pd.Series(dtype=str)).astype(str).str.strip()
    df['kit_plan'] = pd.to_numeric(df.get('KIT A SER INSTALADO RI',
                     pd.Series(dtype=str)), errors='coerce')
    df['aps_plan'] = pd.to_numeric(df.get('AP ADICIONAL RI',
                     pd.Series(dtype=str)), errors='coerce').fillna(0)
    df['fab_exec'] = df.get('Fornecedor de Equipamento',
                     pd.Series(dtype=str)).astype(str).apply(_parse_fab)
    return df[df['inep'].str.match(r'^\d{7,8}$', na=False)][
        ['inep','parceiro','fase','uf','kit_plan','aps_plan','fab_exec']].copy()

# ── Cálculo de desvio (σ) por fase ───────────────────────────────────────────
@st.cache_data(ttl=600)
def calc_desvio_fase(df_circ):
    """
    Compara APs totais planejados vs implementados por escola (instaladas).
    Retorna: desvio médio (bias) e σ por fase, como fator multiplicador.
    """
    inst = df_circ[df_circ['status'].isin(STATUS_INSTALADO)].copy()
    inst = inst[(inst['kit_plan'].notna()) & (inst['kit_impl'].notna())]
    inst['total_plan'] = inst['kit_plan'] + inst['aps_plan']
    inst['total_impl'] = inst['kit_impl'] + inst['aps_impl']
    inst = inst[inst['total_plan'] > 0]
    inst['desvio_pct'] = (inst['total_impl'] - inst['total_plan']) / inst['total_plan']

    result = {}
    for fase, grp in inst.groupby('fase'):
        mu  = float(grp['desvio_pct'].mean())
        sigma = float(grp['desvio_pct'].std())
        n   = len(grp)
        result[fase] = {'bias': mu, 'sigma': sigma, 'n': n}
    return result

# ── Previsão de consumo por parceiro × item ───────────────────────────────────
def calc_previsao(df_circ, df_exec, df_topo, desvio_fase):
    """
    Para cada escola 'a instalar': determina kit + APs → busca topologia → soma itens.
    Retorna DataFrame: parceiro, fase, uf, item, funcao, qtd_prevista.
    """
    a_inst = df_circ[df_circ['status'].isin(STATUS_A_INSTALAR)].copy()

    # Enriquece com parceiro/kit da Divisão por Parceiros se não veio do circuitos
    sem_parceiro = a_inst['parceiro'].str.strip().isin(['','nan','None',''])
    if sem_parceiro.any():
        exec_map = df_exec.set_index('inep')[['parceiro','kit_plan','aps_plan','fab_exec']]
        a_inst.loc[sem_parceiro, 'parceiro'] = a_inst.loc[sem_parceiro, 'inep'].map(
            exec_map['parceiro'])
        a_inst.loc[a_inst['kit_plan'].isna(), 'kit_plan'] = a_inst.loc[
            a_inst['kit_plan'].isna(), 'inep'].map(exec_map['kit_plan'])
        a_inst.loc[a_inst['fab'].isna(), 'fab'] = a_inst.loc[
            a_inst['fab'].isna(), 'inep'].map(exec_map['fab_exec'])

    a_inst = a_inst.dropna(subset=['kit_plan','parceiro'])
    a_inst = a_inst[a_inst['parceiro'].str.strip() != '']

    records = []
    for _, row in a_inst.iterrows():
        fase   = row['fase']
        uf     = row['uf']
        fab    = row.get('fab') or ''
        kit_n  = int(row['kit_plan'])
        aps_ad = int(row['aps_plan'])
        parc   = row['parceiro']

        # Busca topologia: fase × fab × uf × kit
        mask = (
            (df_topo['fase'] == fase) &
            (df_topo['kit']  == kit_n)
        )
        if fab:
            mask_fab = mask & (df_topo['fab'] == fab)
            sub = df_topo[mask_fab]
            if sub.empty:
                sub = df_topo[mask]
        else:
            sub = df_topo[mask]

        # Fallback: ignora UF na busca
        if sub.empty:
            mask2 = (df_topo['fase'] == fase) & (df_topo['kit'] == kit_n)
            sub = df_topo[mask2]

        for _, trow in sub.iterrows():
            if trow['qtd'] == 0:
                continue
            qtd = trow['qtd']
            # APs adicionais: cada AP extra = +1 AP, +1 injetor (ou usa switch), +30m cabo
            if trow['funcao'] == 'AP' and aps_ad > 0:
                qtd += aps_ad
            elif trow['funcao'] == 'INJETOR' and aps_ad > 0:
                qtd += aps_ad
            elif trow['funcao'] == 'CABO' and aps_ad > 0:
                qtd += aps_ad * 30

            records.append({
                'parceiro': parc, 'fase': fase, 'uf': uf,
                'item': trow['item'], 'funcao': trow['funcao'],
                'qtd_prevista_base': qtd,
            })

    if not records:
        return pd.DataFrame()

    df_prev = pd.DataFrame(records)
    # Aplica fator de desvio por fase (bias + 1σ de segurança)
    df_prev['bias'] = df_prev['fase'].map(
        lambda f: desvio_fase.get(f, {}).get('bias', 0.0))
    df_prev['sigma'] = df_prev['fase'].map(
        lambda f: desvio_fase.get(f, {}).get('sigma', 0.0))
    # Fator estatístico: (1 + bias) + 0.5σ → cobertura parcial do desvio
    df_prev['fator'] = (1 + df_prev['bias'] + 0.5 * df_prev['sigma']).clip(lower=1.0)
    # Apenas itens que variam com quantidade de APs usam fator
    df_prev['qtd_prevista'] = df_prev.apply(
        lambda r: r['qtd_prevista_base'] * r['fator']
        if r['funcao'] in ('AP','INJETOR','CABO','SWITCH') else r['qtd_prevista_base'],
        axis=1
    ).round(0)

    return df_prev.groupby(['parceiro','fase','item','funcao'], as_index=False).agg(
        qtd_prevista=('qtd_prevista','sum'),
        fator=('fator','mean'),
        bias=('bias','mean'),
        sigma=('sigma','mean'),
    )

# ─────────────────────────────────────────────────────────────────────────────
# INTERFACE
# ─────────────────────────────────────────────────────────────────────────────
sidebar_logo()
page_header("📦 Previsão de Estoque", "Saldo atual × consumo previsto por parceiro e fase")

with st.sidebar:
    st.markdown("---")
    if st.button("🔄 Atualizar dados", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    st.caption(f"Fontes: circuitos RI 22-07 | Topologia | vw_saldo")

# Carrega dados
with st.spinner("Carregando dados..."):
    try:
        df_saldo   = load_saldo()
        df_circ    = load_circuitos()
        df_exec    = load_exec_divisao()
        df_topo    = load_topologia()
        desvio     = calc_desvio_fase(df_circ)
        df_prev    = calc_previsao(df_circ, df_exec, df_topo, desvio)
    except Exception as e:
        st.error(f"Erro ao carregar dados: {e}")
        st.stop()

# ── Filtros ───────────────────────────────────────────────────────────────────
with st.sidebar:
    fases_disp   = sorted(df_circ['fase'].dropna().unique())
    parc_disp    = sorted(df_circ['parceiro'].dropna().unique())
    sel_fases    = st.multiselect("Fase", fases_disp, default=fases_disp)
    sel_parceiros = st.multiselect("Parceiro", parc_disp, default=[])

# ─────────────────────────────────────────────────────────────────────────────
# BLOCO 1 — VISÃO CONSOLIDADA POR FASE
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("## 🌐 Visão Consolidada por Fase")

df_fase_filtrado = df_circ[df_circ['fase'].isin(sel_fases)] if sel_fases else df_circ

consolidado = []
for fase, grp in df_fase_filtrado.groupby('fase'):
    total  = len(grp)
    inst   = int(grp['status'].isin(STATUS_INSTALADO).sum())
    a_ins  = int(grp['status'].isin(STATUS_A_INSTALAR).sum())
    susp   = int(grp['status'].isin(STATUS_SUSPENSO).sum())
    outros = total - inst - a_ins - susp
    pct_exec = round(inst / total * 100, 1) if total > 0 else 0
    consolidado.append({
        'Fase': fase, 'Contratadas': total,
        'Instaladas': inst, 'A Executar': a_ins,
        'Suspensas': susp, 'Outros': outros,
        '% Executado': pct_exec,
    })

df_cons = pd.DataFrame(consolidado).sort_values('Fase')

# KPIs
k1, k2, k3, k4 = st.columns(4)
k1.metric("Total Escolas", f"{df_cons['Contratadas'].sum():,}".replace(',','.'))
k2.metric("Instaladas",    f"{df_cons['Instaladas'].sum():,}".replace(',','.'),
          f"{df_cons['Instaladas'].sum()/df_cons['Contratadas'].sum()*100:.1f}% concluído")
k3.metric("A Executar",    f"{df_cons['A Executar'].sum():,}".replace(',','.'))
k4.metric("Suspensas",     f"{df_cons['Suspensas'].sum():,}".replace(',','.'))

st.dataframe(
    df_cons.style
    .format({'% Executado': '{:.1f}%',
             'Contratadas': '{:,.0f}', 'Instaladas': '{:,.0f}',
             'A Executar': '{:,.0f}', 'Suspensas': '{:,.0f}'})
    .background_gradient(subset=['% Executado'], cmap='RdYlGn', vmin=0, vmax=100),
    use_container_width=True, hide_index=True
)

# Gráfico de barras empilhadas por fase
fig_fase = go.Figure()
cores = {'Instaladas':'#2ca02c','A Executar':'#1f77b4',
         'Suspensas':'#d62728','Outros':'#aec7e8'}
for col, cor in cores.items():
    fig_fase.add_trace(go.Bar(
        name=col, x=df_cons['Fase'], y=df_cons[col],
        marker_color=cor, text=df_cons[col],
        textposition='auto'
    ))
fig_fase.update_layout(
    barmode='stack', height=340,
    title='Distribuição de Escolas por Fase',
    legend=dict(orientation='h', y=-0.2),
    margin=dict(t=40,b=0,l=0,r=0)
)
st.plotly_chart(fig_fase, use_container_width=True)

# ─────────────────────────────────────────────────────────────────────────────
# BLOCO 2 — DESVIO ESTATÍSTICO POR FASE
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("## 📊 Parâmetros Estatísticos de Desvio")
st.caption("Baseado em escolas já instaladas: desvio entre APs planejados e implementados. "
           "Fator aplicado na previsão de consumo das escolas a executar.")

dev_rows = []
for fase, d in desvio.items():
    dev_rows.append({
        'Fase': fase,
        'N amostras': d['n'],
        'Desvio médio (bias)': f"{d['bias']*100:+.1f}%",
        'Desvio padrão (σ)': f"{d['sigma']*100:.1f}%",
        'Fator aplicado': f"{(1 + d['bias'] + 0.5*d['sigma']):.3f}×",
        'Alerta': '⚠️ Alto desvio' if abs(d['bias']) > 0.15 else ''
    })

if dev_rows:
    df_dev = pd.DataFrame(dev_rows).sort_values('Fase')
    st.dataframe(df_dev, use_container_width=True, hide_index=True)
else:
    st.info("Dados insuficientes para calcular desvio (necessário KIT planejado e implementado).")

# ─────────────────────────────────────────────────────────────────────────────
# BLOCO 3 — PREVISÃO POR PARCEIRO × ITEM (FAROL)
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("## 🚦 Farol de Estoque por Parceiro")

if df_prev.empty:
    st.warning("Sem dados de previsão. Verifique se o arquivo de circuitos tem KIT planejado preenchido.")
else:
    # Aplica filtros
    df_prev_f = df_prev.copy()
    if sel_fases:
        df_prev_f = df_prev_f[df_prev_f['fase'].isin(sel_fases)]
    if sel_parceiros:
        df_prev_f = df_prev_f[df_prev_f['parceiro'].isin(sel_parceiros)]

    # Agrega saldo por parceiro × item (vw_saldo tem: parceiro, item, fase, saldo_atual)
    if not df_saldo.empty and 'parceiro' in df_saldo.columns and 'item' in df_saldo.columns:
        saldo_agg = df_saldo.groupby(['parceiro','item'], as_index=False)['saldo_atual'].sum()
    else:
        saldo_agg = pd.DataFrame(columns=['parceiro','item','saldo_atual'])

    # Agrega previsão por parceiro × item
    prev_agg = df_prev_f.groupby(['parceiro','item','funcao'], as_index=False).agg(
        qtd_prevista=('qtd_prevista','sum'),
        fator=('fator','first'),
    )

    # Join
    farol = prev_agg.merge(saldo_agg, on=['parceiro','item'], how='left')
    farol['saldo_atual'] = farol['saldo_atual'].fillna(0)
    farol['saldo_liquido'] = farol['saldo_atual'] - farol['qtd_prevista']

    def _status(row):
        liq = row['saldo_liquido']
        prev = row['qtd_prevista']
        if liq < 0:
            return '🔴 Falta'
        elif prev > 0 and liq > prev * 0.3:
            return '🟡 Sobra'
        else:
            return '🟢 Adequado'

    farol['Status'] = farol.apply(_status, axis=1)

    # Filtro por status
    with st.sidebar:
        st.markdown("---")
        sel_status = st.multiselect("Status farol",
            ['🔴 Falta','🟢 Adequado','🟡 Sobra'],
            default=['🔴 Falta','🟢 Adequado','🟡 Sobra'])
    if sel_status:
        farol_f = farol[farol['Status'].isin(sel_status)]
    else:
        farol_f = farol

    # KPIs farol
    n_falta = int((farol['Status'] == '🔴 Falta').sum())
    n_ok    = int((farol['Status'] == '🟢 Adequado').sum())
    n_sobra = int((farol['Status'] == '🟡 Sobra').sum())
    c1, c2, c3 = st.columns(3)
    c1.metric("🔴 Com falta",  n_falta)
    c2.metric("🟢 Adequado",   n_ok)
    c3.metric("🟡 Com sobra",  n_sobra)

    # Tabela principal
    cols_show = ['parceiro','fase','item','funcao',
                 'saldo_atual','qtd_prevista','saldo_liquido','fator','Status']
    rename = {
        'parceiro':'Parceiro','fase':'Fase','item':'Item','funcao':'Função',
        'saldo_atual':'Saldo Atual','qtd_prevista':'Previsão Consumo',
        'saldo_liquido':'Saldo Líquido','fator':'Fator Desvio','Status':'Status'
    }
    df_show = farol_f[[c for c in cols_show if c in farol_f.columns]].rename(columns=rename)

    def _color_status(val):
        if '🔴' in str(val):  return 'background-color:#ffcccc;color:#900'
        if '🟡' in str(val):  return 'background-color:#fff3cc;color:#760'
        if '🟢' in str(val):  return 'background-color:#ccffcc;color:#060'
        return ''

    def _color_liq(val):
        try:
            v = float(val)
            if v < 0:  return 'color:#cc0000;font-weight:bold'
            if v > 0:  return 'color:#006600'
        except: pass
        return ''

    st.dataframe(
        df_show.style
        .map(_color_status, subset=['Status'])
        .map(_color_liq,    subset=['Saldo Líquido'])
        .format({
            'Saldo Atual':       '{:,.0f}',
            'Previsão Consumo':  '{:,.0f}',
            'Saldo Líquido':     '{:,.0f}',
            'Fator Desvio':      '{:.3f}×',
        }),
        use_container_width=True, hide_index=True, height=500,
    )

    # Download
    st.download_button(
        "⬇️ Exportar Farol (.csv)",
        data=df_show.to_csv(index=False).encode('utf-8'),
        file_name="previsao_estoque.csv", mime='text/csv'
    )

    # ── Gráfico: top itens com falta ─────────────────────────────────────────
    faltas = farol[farol['Status']=='🔴 Falta'].copy()
    if not faltas.empty:
        st.markdown("### 🔴 Itens com Falta — Top por Déficit")
        faltas['deficit'] = (-faltas['saldo_liquido']).round(0)
        top_faltas = (faltas.groupby(['item','parceiro'], as_index=False)['deficit']
                      .sum().sort_values('deficit', ascending=False).head(20))
        fig_falta = px.bar(
            top_faltas, x='deficit', y='item', color='parceiro',
            orientation='h', height=420,
            labels={'deficit':'Déficit (un)','item':'Item','parceiro':'Parceiro'},
            title='Top 20 itens com maior déficit de estoque',
            color_discrete_sequence=px.colors.qualitative.Set2,
        )
        fig_falta.update_layout(margin=dict(t=40,b=0,l=0,r=0))
        st.plotly_chart(fig_falta, use_container_width=True)

    # ── Resumo por parceiro ───────────────────────────────────────────────────
    st.markdown("### 📋 Resumo por Parceiro")
    resumo_parc = farol.groupby('parceiro').agg(
        total_itens=('item','count'),
        itens_falta=('Status', lambda x: (x=='🔴 Falta').sum()),
        itens_ok=('Status', lambda x: (x=='🟢 Adequado').sum()),
        itens_sobra=('Status', lambda x: (x=='🟡 Sobra').sum()),
    ).reset_index()
    resumo_parc['% Crítico'] = (
        resumo_parc['itens_falta'] / resumo_parc['total_itens'] * 100
    ).round(1)
    resumo_parc = resumo_parc.sort_values('itens_falta', ascending=False)
    st.dataframe(
        resumo_parc.rename(columns={
            'parceiro':'Parceiro','total_itens':'Total Itens',
            'itens_falta':'🔴 Falta','itens_ok':'🟢 Adequado',
            'itens_sobra':'🟡 Sobra','% Crítico':'% Crítico'
        }).style.format({'% Crítico':'{:.1f}%'})
          .background_gradient(subset=['% Crítico'], cmap='RdYlGn_r', vmin=0, vmax=100),
        use_container_width=True, hide_index=True
    )

# ─────────────────────────────────────────────────────────────────────────────
# BLOCO 4 — ESCOLAS A EXECUTAR POR PARCEIRO
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("## 🏫 Escolas a Executar por Parceiro")

df_a_inst = df_circ[
    df_circ['status'].isin(STATUS_A_INSTALAR) &
    df_circ['fase'].isin(sel_fases if sel_fases else df_circ['fase'].unique())
].copy()

if sel_parceiros:
    df_a_inst = df_a_inst[df_a_inst['parceiro'].isin(sel_parceiros)]

resumo_escolas = (df_a_inst
    .groupby(['parceiro','fase','status'])
    .size().reset_index(name='escolas')
    .sort_values(['parceiro','fase','escolas'], ascending=[True,True,False])
)

if resumo_escolas.empty:
    st.info("Nenhuma escola a executar com os filtros selecionados.")
else:
    # Pivot: parceiro × fase → total
    pivot = resumo_escolas.pivot_table(
        index=['parceiro','fase'], columns='status', values='escolas', fill_value=0
    ).reset_index()
    pivot.columns.name = None
    pivot['Total'] = pivot.drop(columns=['parceiro','fase']).sum(axis=1)
    pivot = pivot.sort_values(['parceiro','Total'], ascending=[True,False])
    st.dataframe(pivot, use_container_width=True, hide_index=True)
    st.caption(f"Total: {df_a_inst.shape[0]:,} escolas a executar em {df_a_inst['parceiro'].nunique()} parceiros")
