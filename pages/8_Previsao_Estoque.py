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

STATUS_INSTALADO  = {'Ativo', 'Instalado'}
STATUS_A_INSTALAR = {'Circuito com Contrato Fechado', 'Agendado',
                     'Implantação em andamento', 'Instalado com Pendência'}
STATUS_SUSPENSO   = {'Em Reforma', 'Cancelado', 'Suspenso'}

def _norm_fase(f):
    f = str(f).strip().upper()
    if 'ADIC' in f: return '4.2 ADICIONAL'
    if '5.0' in f or 'KONEKTA' in f or 'FASE 2' in f or 'FASE 3' in f or 'FASE 4' in f or 'FASE 5' in f: return '5.0'
    if '4.2' in f: return '4.2'
    if '4.1' in f or 'FASE 1' in f: return '4.1'
    if 'SAT' in f: return 'SATÉLITE'
    return f

# ─────────────────────────────────────────────────────────────────────────────
# CARGA (tudo do Supabase)
# ─────────────────────────────────────────────────────────────────────────────
@st.cache_resource
def get_sb():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

def _load_all(table, select='*'):
    sb = get_sb()
    rows, page, size = [], 0, 1000
    while True:
        r = sb.table(table).select(select).range(page*size, (page+1)*size-1).execute()
        if not r.data: break
        rows.extend(r.data)
        page += 1
    return pd.DataFrame(rows)

@st.cache_data(ttl=600)
def load_circuitos():
    df = _load_all('circuitos_ri')
    if df.empty: return df
    df['fase'] = df['fase_raw'].apply(_norm_fase)
    for c in ['kit_plan','aps_plan','kit_impl','aps_impl']:
        df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0)
    return df

@st.cache_data(ttl=3600)
def load_topologia():
    df = _load_all('topologia_kit')
    if df.empty: return df
    df['fase_norm'] = df['fase'].apply(_norm_fase)
    df['qtd'] = pd.to_numeric(df['qtd'], errors='coerce').fillna(0)
    df['kit_num'] = pd.to_numeric(df['kit_num'], errors='coerce')
    return df

@st.cache_data(ttl=3600)
def load_exec():
    df = _load_all('exec_inep_parceiro')
    if df.empty: return df
    df['fase'] = df['lote'].apply(_norm_fase)
    for c in ['kit_plan','aps_plan']:
        df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0)
    return df

def _item_to_funcao(nome):
    """Normaliza nome do item (vw_saldo) para funcao da topologia."""
    n = str(nome).upper().strip()
    if 'POE' in n or 'INJETOR' in n:   return 'INJETOR'
    if 'CABO' in n:                     return 'CABO'
    if 'NOBREAK' in n:                  return 'NOBREAK'
    if 'RACK 5U' in n:                  return 'RACK 5U'
    if 'RACK 8U' in n:                  return 'RACK 8U'
    if 'RACK OUT' in n:                 return 'RACK OUTDOOR'
    if 'BANDEJA' in n:                  return 'BANDEJA'
    if 'ORGANIZ' in n:                  return 'ORGANIZADOR'
    if 'SWITCH' in n:                   return 'SWITCH'
    if 'VENTIL' in n:                   return 'VENTILADORES'
    if 'SIMET' in n:                    return 'SIMET'
    if 'CONTROLADORA' in n:             return 'CONTROLADORA'
    if 'AP' in n or 'ACCESS' in n or 'ROTEADOR EMPRESARIAL' in n: return 'AP'
    if 'ROTEADOR' in n or 'GATEWAY' in n: return 'ROTEADOR'
    return n

@st.cache_data(ttl=600)
def load_saldo():
    """Retorna saldo agregado por parceiro × funcao."""
    df = _load_all('vw_saldo')
    if df.empty:
        return df
    df['saldo_atual'] = pd.to_numeric(df.get('saldo_atual', 0), errors='coerce').fillna(0)
    if 'item' not in df.columns:
        return df
    df['funcao'] = df['item'].apply(_item_to_funcao)
    group_cols = ['parceiro','funcao'] + (['fase'] if 'fase' in df.columns else [])
    return df.groupby(group_cols, as_index=False)['saldo_atual'].sum()

# ─────────────────────────────────────────────────────────────────────────────
# CÁLCULOS
# ─────────────────────────────────────────────────────────────────────────────
def calc_desvio(df_circ):
    """σ e bias de desvio entre APs planejados vs. implementados por fase."""
    inst = df_circ[df_circ['situacao'] == 'Instalado'].copy()
    inst = inst[(inst['kit_plan'] > 0) & (inst['kit_impl'] > 0)]
    inst['total_plan'] = inst['kit_plan'] + inst['aps_plan']
    inst['total_impl'] = inst['kit_impl'] + inst['aps_impl']
    inst = inst[inst['total_plan'] > 0]
    inst['desvio_pct'] = (inst['total_impl'] - inst['total_plan']) / inst['total_plan']

    result = {}
    for fase, grp in inst.groupby('fase'):
        result[fase] = {
            'bias':  float(grp['desvio_pct'].mean()),
            'sigma': float(grp['desvio_pct'].std()) if len(grp) > 1 else 0.0,
            'n':     len(grp),
        }
    return result

FUNCOES_VARIAVEIS = {'AP', 'AP OUTDOOR', 'INJETOR', 'CABO'}

def calc_previsao(df_circ, df_exec, df_topo, desvio):
    """Consumo previsto por parceiro × item para escolas 'A Instalar'."""
    a_inst = df_circ[df_circ['situacao'] == 'A Instalar'].copy()

    # Preenche parceiro/kit ausentes com dados da Execução
    faltam = a_inst['parceiro'].isna() | a_inst['parceiro'].str.strip().isin(['','nan'])
    if faltam.any() and not df_exec.empty:
        idx = df_exec.set_index('inep')
        for col in ['parceiro','kit_plan','aps_plan','fabricante']:
            if col in idx.columns:
                a_inst.loc[faltam, col] = a_inst.loc[faltam,'inep'].map(idx[col])

    a_inst = a_inst[a_inst['kit_plan'] > 0].dropna(subset=['parceiro'])
    a_inst = a_inst[a_inst['parceiro'].str.strip() != '']

    if a_inst.empty or df_topo.empty:
        return pd.DataFrame()

    records = []
    for _, row in a_inst.iterrows():
        fase  = row['fase']
        fab   = str(row.get('fabricante') or '').strip().upper()
        kit_n = int(row['kit_plan'])
        ad    = int(row['aps_plan'])
        parc  = row['parceiro']
        uf    = str(row.get('uf') or '').strip().upper()

        # Busca topologia: fase_norm × kit_num × UF × fabricante
        mask_base = (df_topo['fase_norm'] == fase) & (df_topo['kit_num'] == kit_n)
        # 1ª tentativa: fase + kit + UF + fabricante
        sub = pd.DataFrame()
        if uf and fab:
            sub = df_topo[mask_base
                          & df_topo['uf'].str.upper().str.strip().eq(uf)
                          & df_topo['fabricante'].str.upper().eq(fab)]
        # 2ª: fase + kit + UF
        if sub.empty and uf:
            sub = df_topo[mask_base & df_topo['uf'].str.upper().str.strip().eq(uf)]
        # 3ª: fase + kit + fabricante
        if sub.empty and fab:
            sub = df_topo[mask_base & df_topo['fabricante'].str.upper().eq(fab)]
        # fallback: apenas fase + kit (pega primeira UF disponível para evitar duplicar)
        if sub.empty:
            sub = df_topo[mask_base]
            if not sub.empty:
                primeira_uf = sub['uf'].iloc[0]
                sub = sub[sub['uf'] == primeira_uf]
        if sub.empty:
            continue

        for _, tr in sub.iterrows():
            if tr['qtd'] == 0: continue
            qtd = float(tr['qtd'])
            fc  = str(tr['funcao']).strip().upper()
            if fc == 'AP'      and ad > 0: qtd += ad
            elif fc == 'INJETOR' and ad > 0: qtd += ad
            elif fc == 'CABO'  and ad > 0: qtd += ad * 30
            records.append({'parceiro': parc, 'fase': fase,
                            'funcao': fc, 'qtd_base': qtd})

    if not records:
        return pd.DataFrame()

    df_p = pd.DataFrame(records)
    df_p['bias']  = df_p['fase'].map(lambda f: desvio.get(f,{}).get('bias',  0.0))
    df_p['sigma'] = df_p['fase'].map(lambda f: desvio.get(f,{}).get('sigma', 0.0))
    # Fator estatístico: apenas itens que variam com APs
    df_p['fator'] = df_p.apply(
        lambda r: max(1.0, 1 + r['bias'] + 0.5*r['sigma'])
        if r['funcao'] in FUNCOES_VARIAVEIS else 1.0, axis=1)
    df_p['qtd_prevista'] = (df_p['qtd_base'] * df_p['fator']).round(0)

    return df_p.groupby(['parceiro','fase','funcao'], as_index=False).agg(
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

with st.spinner("Carregando dados do Supabase..."):
    try:
        df_circ = load_circuitos()
        df_exec = load_exec()
        df_topo = load_topologia()
        df_saldo = load_saldo()
    except Exception as e:
        st.error(f"Erro ao carregar: {e}")
        st.stop()

if df_circ.empty:
    st.warning("Tabela `circuitos_ri` vazia. Execute o ETL `construir_modelo_financeiro.py` para popular.")
    st.stop()

desvio = calc_desvio(df_circ)
df_prev = calc_previsao(df_circ, df_exec, df_topo, desvio)

# ── Filtros ───────────────────────────────────────────────────────────────────
with st.sidebar:
    fases_disp = sorted(df_circ['fase'].dropna().unique())
    parc_disp  = sorted(df_circ['parceiro'].dropna().unique())
    sel_fases  = st.multiselect("Fase", fases_disp, default=fases_disp, key='flt_fase')
    sel_parc   = st.multiselect("Parceiro", parc_disp, default=[], key='flt_parc')
    st.markdown("---")
    sel_status_farol = st.multiselect("Status farol",
        ['🔴 Falta','🟢 Adequado','🟡 Sobra'],
        default=['🔴 Falta','🟢 Adequado','🟡 Sobra'])

df_f = df_circ[df_circ['fase'].isin(sel_fases)] if sel_fases else df_circ
if sel_parc:
    df_f = df_f[df_f['parceiro'].isin(sel_parc)]

# ─────────────────────────────────────────────────────────────────────────────
# BLOCO 1 — CONSOLIDADO POR FASE
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("## 🌐 Visão Consolidada por Fase")

cons = []
for fase, grp in df_f.groupby('fase'):
    tot  = len(grp)
    inst = int(grp['situacao'].eq('Instalado').sum())
    ains = int(grp['situacao'].eq('A Instalar').sum())
    susp = int(grp['situacao'].eq('Suspenso').sum())
    out  = tot - inst - ains - susp
    cons.append({'Fase': fase, 'Contratadas': tot, 'Instaladas': inst,
                 'A Executar': ains, 'Suspensas': susp, 'Outros': out,
                 '% Executado': round(inst/tot*100,1) if tot else 0})
df_cons = pd.DataFrame(cons).sort_values('Fase')

k1,k2,k3,k4 = st.columns(4)
k1.metric("Total Escolas",  f"{df_cons['Contratadas'].sum():,.0f}".replace(',','.'))
k2.metric("✅ Instaladas",  f"{df_cons['Instaladas'].sum():,.0f}".replace(',','.'),
          f"{df_cons['Instaladas'].sum()/max(df_cons['Contratadas'].sum(),1)*100:.1f}%")
k3.metric("🔧 A Executar",  f"{df_cons['A Executar'].sum():,.0f}".replace(',','.'))
k4.metric("⏸ Suspensas",   f"{df_cons['Suspensas'].sum():,.0f}".replace(',','.'))

st.dataframe(
    df_cons.style
    .format({'% Executado':'{:.1f}%','Contratadas':'{:,.0f}','Instaladas':'{:,.0f}',
             'A Executar':'{:,.0f}','Suspensas':'{:,.0f}','Outros':'{:,.0f}'})
    .background_gradient(subset=['% Executado'], cmap='RdYlGn', vmin=0, vmax=100),
    use_container_width=True, hide_index=True
)

fig_bar = go.Figure()
for col, cor in [('Instaladas','#2ca02c'),('A Executar','#1f77b4'),
                 ('Suspensas','#d62728'),('Outros','#aec7e8')]:
    fig_bar.add_trace(go.Bar(name=col, x=df_cons['Fase'], y=df_cons[col],
                             marker_color=cor, text=df_cons[col], textposition='auto'))
fig_bar.update_layout(barmode='stack', height=320,
                      title='Distribuição de Escolas por Fase',
                      legend=dict(orientation='h', y=-0.25),
                      margin=dict(t=40,b=0,l=0,r=0))
st.plotly_chart(fig_bar, use_container_width=True)

# ─────────────────────────────────────────────────────────────────────────────
# BLOCO 2 — PARÂMETROS ESTATÍSTICOS
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("## 📊 Parâmetros Estatísticos de Desvio")
st.caption("Desvio entre APs planejados × implementados nas escolas já instaladas. "
           "Fator = (1 + bias + 0,5σ) aplicado sobre itens variáveis (AP, injetor, cabo) na previsão.")

dev_rows = []
for fase, d in sorted(desvio.items()):
    fator = max(1.0, 1 + d['bias'] + 0.5*d['sigma'])
    dev_rows.append({
        'Fase': fase,
        'N amostras': d['n'],
        'Desvio médio (bias)': f"{d['bias']*100:+.1f}%",
        'Desvio padrão (σ)':   f"{d['sigma']*100:.1f}%",
        'Fator aplicado':      f"{fator:.3f}×",
        '⚠️': '⚠️ Alto desvio' if abs(d['bias']) > 0.15 else '',
    })
if dev_rows:
    st.dataframe(pd.DataFrame(dev_rows), use_container_width=True, hide_index=True)
else:
    st.info("Sem dados de desvio — necessário KIT planejado e implementado preenchidos em `circuitos_ri`.")

# ─────────────────────────────────────────────────────────────────────────────
# BLOCO 3 — FAROL DE ESTOQUE
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("## 🚦 Farol de Estoque por Parceiro × Item")

if df_prev.empty:
    st.warning("Previsão vazia. Verifique se `circuitos_ri` e `topologia_kit` estão populadas.")
else:
    df_pf = df_prev.copy()
    if sel_fases: df_pf = df_pf[df_pf['fase'].isin(sel_fases)]
    if sel_parc:  df_pf = df_pf[df_pf['parceiro'].isin(sel_parc)]

    # Saldo por parceiro × funcao (vw_saldo.item mapeado para funcao)
    if not df_saldo.empty and 'funcao' in df_saldo.columns:
        # Se vw_saldo tiver coluna 'fase', filtra por ela também
        if 'fase' in df_saldo.columns:
            sal_agg = df_saldo.groupby(['parceiro','fase','funcao'], as_index=False)['saldo_atual'].sum()
            merge_keys = ['parceiro','fase','funcao']
        else:
            sal_agg = df_saldo[['parceiro','funcao','saldo_atual']]
            merge_keys = ['parceiro','funcao']
    else:
        sal_agg = pd.DataFrame(columns=['parceiro','funcao','saldo_atual'])
        merge_keys = ['parceiro','funcao']

    prev_agg = df_pf.groupby(['parceiro','fase','funcao'], as_index=False).agg(
        qtd_prevista=('qtd_prevista','sum'),
        fator=('fator','first'),
        bias=('bias','first'),
        sigma=('sigma','first'),
    )

    farol = prev_agg.merge(sal_agg, on=merge_keys, how='left')
    farol['saldo_atual']  = farol['saldo_atual'].fillna(0)
    farol['saldo_liquido'] = farol['saldo_atual'] - farol['qtd_prevista']

    def _status(r):
        l, p = r['saldo_liquido'], r['qtd_prevista']
        if l < 0:                        return '🔴 Falta'
        if p > 0 and l > p * 0.30:      return '🟡 Sobra'
        return '🟢 Adequado'

    farol['Status'] = farol.apply(_status, axis=1)

    n_f = int((farol['Status']=='🔴 Falta').sum())
    n_a = int((farol['Status']=='🟢 Adequado').sum())
    n_s = int((farol['Status']=='🟡 Sobra').sum())
    c1,c2,c3 = st.columns(3)
    c1.metric("🔴 Com falta", n_f)
    c2.metric("🟢 Adequado",  n_a)
    c3.metric("🟡 Com sobra", n_s)

    farol_show = farol[farol['Status'].isin(sel_status_farol)] if sel_status_farol else farol

    rename = {
        'parceiro':'Parceiro','fase':'Fase','funcao':'Tipo de Item',
        'saldo_atual':'Saldo Atual','qtd_prevista':'Prev. Consumo',
        'saldo_liquido':'Saldo Líquido','fator':'Fator σ','Status':'Status'
    }
    cols = [c for c in ['parceiro','fase','funcao','saldo_atual',
                        'qtd_prevista','saldo_liquido','fator','Status']
            if c in farol_show.columns]

    def _cs(v):
        if '🔴' in str(v): return 'background-color:#ffcccc;color:#900'
        if '🟡' in str(v): return 'background-color:#fff3cc;color:#760'
        if '🟢' in str(v): return 'background-color:#ccffcc;color:#060'
        return ''
    def _cl(v):
        try:
            return 'color:#cc0000;font-weight:bold' if float(v)<0 else 'color:#006600'
        except: return ''

    st.dataframe(
        farol_show[cols].rename(columns=rename).style
        .map(_cs, subset=['Status'])
        .map(_cl, subset=['Saldo Líquido'])
        .format({'Saldo Atual':'{:,.0f}','Prev. Consumo':'{:,.0f}',
                 'Saldo Líquido':'{:,.0f}','Fator σ':'{:.3f}×'}),
        use_container_width=True, hide_index=True, height=480,
    )

    st.download_button("⬇️ Exportar (.csv)",
        data=farol_show[cols].rename(columns=rename).to_csv(index=False).encode('utf-8'),
        file_name="previsao_estoque.csv", mime='text/csv')

    # Top déficits
    faltas = farol[farol['Status']=='🔴 Falta'].copy()
    if not faltas.empty:
        st.markdown("### 🔴 Top déficits")
        faltas['deficit'] = (-faltas['saldo_liquido']).round(0)
        top = (faltas.groupby(['funcao','parceiro'],as_index=False)['deficit']
               .sum().sort_values('deficit',ascending=False).head(20))
        fig_f = px.bar(top, x='deficit', y='funcao', color='parceiro', orientation='h',
                       height=400, labels={'deficit':'Déficit (un)','funcao':'Tipo de Item'},
                       title='Top 20 — maior déficit de estoque',
                       color_discrete_sequence=px.colors.qualitative.Set2)
        fig_f.update_layout(margin=dict(t=40,b=0,l=0,r=0))
        st.plotly_chart(fig_f, use_container_width=True)

    # Resumo por parceiro
    st.markdown("### 📋 Resumo por Parceiro")
    rp = farol.groupby('parceiro').agg(
        total=('item','count'),
        falta=('Status', lambda x: (x=='🔴 Falta').sum()),
        ok=('Status',   lambda x: (x=='🟢 Adequado').sum()),
        sobra=('Status',lambda x: (x=='🟡 Sobra').sum()),
    ).reset_index()
    rp['% Crítico'] = (rp['falta']/rp['total'].replace(0,1)*100).round(1)
    rp = rp.sort_values('falta', ascending=False)
    st.dataframe(
        rp.rename(columns={'parceiro':'Parceiro','total':'Total',
                            'falta':'🔴 Falta','ok':'🟢 Adequado',
                            'sobra':'🟡 Sobra'})
        .style.format({'% Crítico':'{:.1f}%'})
        .background_gradient(subset=['% Crítico'], cmap='RdYlGn_r', vmin=0, vmax=100),
        use_container_width=True, hide_index=True)

# ─────────────────────────────────────────────────────────────────────────────
# BLOCO 4 — ESCOLAS A EXECUTAR
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("## 🏫 Escolas a Executar por Parceiro")

df_ai = df_f[df_f['situacao'] == 'A Instalar'].copy()
if sel_parc: df_ai = df_ai[df_ai['parceiro'].isin(sel_parc)]

if df_ai.empty:
    st.info("Nenhuma escola a executar com os filtros selecionados.")
else:
    pivot = (df_ai.groupby(['parceiro','fase','status'])
             .size().reset_index(name='N')
             .pivot_table(index=['parceiro','fase'], columns='status', values='N', fill_value=0)
             .reset_index())
    pivot.columns.name = None
    pivot['Total'] = pivot.drop(columns=['parceiro','fase'], errors='ignore').sum(axis=1)
    pivot = pivot.sort_values(['parceiro','Total'], ascending=[True,False])
    st.dataframe(pivot, use_container_width=True, hide_index=True)
    st.caption(f"Total: {len(df_ai):,} escolas a executar | {df_ai['parceiro'].nunique()} parceiros")
