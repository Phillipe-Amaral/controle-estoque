"""Dashboards Board EACE — acompanhamento executivo por fase."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
import streamlit as st
from supabase import create_client
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from utils.tema_iuh import aplicar_tema, sidebar_logo, page_header

st.set_page_config(page_title="Dashboards Board | IUH Digital", page_icon="📊", layout="wide")
aplicar_tema()

SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]

# ── Paleta IUH ────────────────────────────────────────────────────────────────
TEAL    = "#0C6679"
ACCENT  = "#2EDBA0"
DARK    = "#0a4a5a"
SLATE   = "#64748b"
VERDE   = "#38A169"
ROJO    = "#E53E3E"
AZUL    = "#3182CE"

EXCEL_RE_PATH = r"C:\Users\Usuário\OneDrive - IUH DIGITAL LTDA\Corporativo - 6.01 Compras_e_Contratações\Rede Externa\FASE 4.2 e 5.0- PLANILHA GERAL DE COMPRAS.xlsx"

FASE_ORDER  = ["4.1", "4.2", "4.2 ADICIONAL", "5.0"]
FASE_LABELS = {"4.1": "Fase 4.1", "4.2": "Fase 4.2", "4.2 ADICIONAL": "Fase 4.2 Ad.", "5.0": "Fase 5.0"}
FASE_CORES  = {"4.1": TEAL, "4.2": ACCENT, "4.2 ADICIONAL": AZUL, "5.0": DARK}

# ── Dados estáticos (TABELA FINANCEIRA — última atualização 17/08/2026) ────────
ESTOQUE = {
    "Fase 4.1":   10_067_880,
    "Fase 4.2":    5_900_127,
    "Fase 4.2 Ad.":  442_048,
    "Fase 5.0":   15_484_285,
}

# Scatter: média de AP's instalados × cabo consumido por AP (m)
SCATTER = {
    "Fase 4.1":           {"aps": 3.67, "cabo_por_ap": 35.1, "escolas": 1_417},
    "Fase 4.2":           {"aps": 3.81, "cabo_por_ap": 26.0, "escolas": 1_252},
    "Fase 4.2 Adicional": {"aps": 3.59, "cabo_por_ap": 29.1, "escolas":   169},
    "Fase 5.0":           {"aps": 6.36, "cabo_por_ap": 40.4, "escolas": 1_145},
}

# Transportes 2026 (TRANSPORTES 2026 — TABELA FINANCEIRA)
TRANSPORTES = {
    "FLEX CARGO LTDA ME":           65,
    "BRASPRESS TRANSPORTES":        13,
    "LOGGO SOLUÇÕES LOGÍSTICAS":    12,
    "EAGLE SOLUÇÕES LOGÍSTICAS":    10,
    "L4B LOGÍSTICA LTDA":            9,
    "FLEX CARGO LTDA":               8,
    "BRINGER DO BRASIL":             4,
    "A. R. T. TÁXI AÉREO":           1,
    "GUERINO SEISCENTO":             1,
    "RODOVIÁRIO CAMILO DOS SANTOS":  1,
    "UNIÃO TRANSPORTE DE ENCOM.":    1,
    "VITA AIR CARGO":                1,
}

# ── Supabase ──────────────────────────────────────────────────────────────────
@st.cache_resource
def get_client():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

sb = get_client()

@st.cache_data(ttl=3600)
def carregar_dados_re_supabase():
    """Carrega dados de análise RE do Supabase (financeiro_inep)."""
    cols = "inep,uf,municipio,fase,custo_mensal_re_real,custo_inst_re_real,custo_24m_re_real,classificacao_re,fornecedor_re,velocidade_re,localizacao_re"
    rows_all, offset = [], 0
    while True:
        r = sb.table("financeiro_inep").select(cols).range(offset, offset + 999).execute()
        rows_all.extend(r.data)
        if len(r.data) < 1000: break
        offset += 1000
    rows = []
    for rec in rows_all:
        custo = rec.get("custo_mensal_re_real")
        uf    = rec.get("uf")
        if not uf or not custo or not isinstance(custo, (int, float)) or custo <= 0:
            continue
        vel_num = rec.get("velocidade_re") or 0
        try: vel_num = float(vel_num)
        except: vel_num = 0
        if vel_num <= 50:     vel_faixa = "≤50 Mbps"
        elif vel_num <= 100:  vel_faixa = "51-100 Mbps"
        elif vel_num <= 200:  vel_faixa = "101-200 Mbps"
        elif vel_num <= 500:  vel_faixa = "201-500 Mbps"
        else:                 vel_faixa = ">500 Mbps"
        clf = str(rec.get("classificacao_re") or "").strip().title() or "Não informado"
        loc = str(rec.get("localizacao_re") or "").strip().upper() or "NÃO INFORMADO"
        rows.append({
            "fase":         str(rec.get("fase") or "").strip(),
            "uf":           str(uf).strip(),
            "municipio":    str(rec.get("municipio") or "").strip(),
            "velocidade":   vel_num,
            "vel_faixa":    vel_faixa,
            "classificacao": clf,
            "fornecedor":   str(rec.get("fornecedor_re") or "").strip(),
            "mensalidade":  float(custo),
            "instalacao":   float(rec.get("custo_inst_re_real") or 0),
            "custo_24m":    float(rec.get("custo_24m_re_real") or 0),
            "localizacao":  loc,
        })
    return pd.DataFrame(rows)

@st.cache_data(ttl=600)
def carregar_financeiro():
    rows, page, size = [], 0, 1000
    while True:
        r = (sb.table("financeiro_inep")
               .select("*")
               .range(page * size, (page + 1) * size - 1)
               .execute())
        if not r.data:
            break
        rows.extend(r.data)
        page += 1
    df = pd.DataFrame(rows)
    num_skip = {
        "inep", "escola", "uf", "municipio", "fase", "lote",
        "parceiro_ri", "responsavel_re", "fornecedor_re", "classificacao_re",
        "status_circuito_re", "kit_previsto", "kit_real",
        "status_parcial", "status_rdo", "updated_at",
        "data_inst_ri", "data_manut_ri", "data_inst_re", "data_rdo",
    }
    for c in df.columns:
        if c not in num_skip:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)
    df["fase"] = df["fase"].fillna("").str.strip()
    for col in ["data_inst_ri", "data_inst_re", "data_rdo"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")
    return df

# ── Header ────────────────────────────────────────────────────────────────────
page_header(
    "Dashboards Board — EACE",
    "Panorama de contratações, investimentos e eficiência operacional · Fases 4.1 a 5.0",
)

df_all = carregar_financeiro()
if df_all.empty:
    st.error("Sem dados em financeiro_inep.")
    st.stop()

# ── Sidebar ───────────────────────────────────────────────────────────────────
sidebar_logo("Dashboards Board")
with st.sidebar:
    st.markdown("### Filtros")
    fases_disp = [f for f in FASE_ORDER if f in df_all["fase"].unique()]
    fases_sel  = st.multiselect("Fase", fases_disp, default=fases_disp)
    ufs_disp   = sorted(df_all["uf"].dropna().unique())
    ufs_sel    = st.multiselect("UF", ufs_disp, default=ufs_disp)

df = df_all[df_all["fase"].isin(fases_sel) & df_all["uf"].isin(ufs_sel)].copy()

# ── Helpers ───────────────────────────────────────────────────────────────────
def brl(v, milhoes=False):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "—"
    v = float(v)
    if milhoes and abs(v) >= 1e6:
        return f"R$ {v/1e6:.1f}M"
    if abs(v) >= 1e3:
        return "R$ " + f"{v:,.0f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {v:.0f}"

def base_layout(fig, title="", height=380, showlegend=True):
    fig.update_layout(
        title=dict(text=title, font=dict(size=13, color=DARK, family="Segoe UI"),
                   x=0, xanchor="left", pad=dict(b=8)),
        paper_bgcolor="white",
        plot_bgcolor="white",
        font=dict(family="Segoe UI, Arial", color="#334155", size=11),
        height=height,
        margin=dict(l=12, r=12, t=44, b=12),
        showlegend=showlegend,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1,
                    font=dict(size=10)),
    )
    fig.update_xaxes(showgrid=False, showline=True, linecolor="#e2e8f0", tickfont=dict(size=10))
    fig.update_yaxes(showgrid=True, gridcolor="#f0f4f8", showline=False, tickfont=dict(size=10))
    return fig

# ── TABS ──────────────────────────────────────────────────────────────────────
tab_geral, tab_re, tab_ri, tab_log = st.tabs([
    "📊 Visão Geral",
    "🌐 Rede Externa",
    "📡 Rede Interna",
    "🚚 Logística",
])

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 1 — VISÃO GERAL
# ═══════════════════════════════════════════════════════════════════════════════
with tab_geral:

    # ── KPIs ──────────────────────────────────────────────────────────────────
    ri_inst  = int(df["data_inst_ri"].notna().sum()) if "data_inst_ri" in df else 0
    re_inst  = int(df["data_inst_re"].notna().sum()) if "data_inst_re" in df else 0
    aps_tot  = int(df["aps_ad_impl"].sum())
    rec_parc = float(df["receita_parcial"].sum())
    cst_parc = float(df["custo_parcial"].sum())
    mrg_parc = float(df["margem_parcial"].sum())

    kc1, kc2, kc3, kc4, kc5, kc6 = st.columns(6)
    kc1.metric("RI's Instaladas", f"{ri_inst:,}".replace(",", "."))
    kc2.metric("RE's Instaladas", f"{re_inst:,}".replace(",", "."))
    kc3.metric("AP's Instalados", f"{aps_tot:,}".replace(",", "."))
    kc4.metric("Receita Parcial", brl(rec_parc, milhoes=True))
    kc5.metric("Custo Parcial",   brl(cst_parc, milhoes=True))
    kc6.metric("Margem Parcial",  brl(mrg_parc, milhoes=True))

    st.markdown("---")
    col_a, col_b = st.columns(2)

    # ── Mix de Contratação RE por Fase (%) ────────────────────────────────────
    with col_a:
        df_mix = (
            df[df["classificacao_re"].notna() & (df["classificacao_re"] != "")]
            .groupby(["fase", "classificacao_re"])
            .size()
            .reset_index(name="qtd")
        )
        df_mix["fase_label"] = df_mix["fase"].map(lambda f: FASE_LABELS.get(f, f))
        df_mix["total"] = df_mix.groupby("fase")["qtd"].transform("sum")
        df_mix["pct"] = df_mix["qtd"] / df_mix["total"] * 100

        fig_mix = go.Figure()
        cores_class = {"Broker": TEAL, "Provedor": ACCENT, "Operadora": AZUL}
        for cls, cor in cores_class.items():
            sub = df_mix[df_mix["classificacao_re"] == cls].sort_values("fase")
            labels = [FASE_LABELS.get(f, f) for f in sub["fase"]]
            pcts   = sub["pct"].round(1).tolist()
            fig_mix.add_bar(
                name=cls,
                x=labels,
                y=pcts,
                marker_color=cor,
                text=[f"{v:.0f}%" for v in pcts],
                textposition="inside",
                textfont=dict(color="white", size=11, family="Segoe UI"),
            )
        fig_mix.update_layout(barmode="stack")
        base_layout(fig_mix, "Mix de Contratação de RE por Fase (%)", height=340)
        fig_mix.update_yaxes(range=[0, 105], ticksuffix="%")
        st.plotly_chart(fig_mix, use_container_width=True)

    # ── Investimento em Estoque RI por Fase ───────────────────────────────────
    with col_b:
        fases_est = [k for k in ["Fase 4.1", "Fase 4.2", "Fase 4.2 Ad.", "Fase 5.0"]
                     if any(f in k for f in fases_sel)]
        vals_est  = [ESTOQUE[k] for k in fases_est]
        cores_est = [list(FASE_CORES.values())[i] for i in range(len(fases_est))]

        fig_est = go.Figure(go.Bar(
            x=fases_est,
            y=vals_est,
            marker_color=cores_est,
            text=[brl(v, milhoes=True) for v in vals_est],
            textposition="outside",
            textfont=dict(size=11, family="Segoe UI"),
        ))
        base_layout(fig_est, "Investimento em Estoque de RI por Fase", height=340, showlegend=False)
        fig_est.update_yaxes(tickformat=".2s", tickprefix="R$ ")
        fig_est.add_annotation(
            text="Fonte: TABELA FINANCEIRA · 17/08/2026",
            xref="paper", yref="paper", x=1, y=-0.08,
            showarrow=False, font=dict(size=9, color=SLATE), xanchor="right",
        )
        st.plotly_chart(fig_est, use_container_width=True)

    # ── Progresso de instalação por fase ─────────────────────────────────────
    st.markdown("#### Progresso de instalação por fase")
    prog_cols = st.columns(len(fases_sel) if fases_sel else 1)
    for i, fase in enumerate(fases_sel):
        dff = df[df["fase"] == fase]
        total   = len(dff)
        ri_ok   = int(dff["data_inst_ri"].notna().sum()) if "data_inst_ri" in dff else 0
        re_ok   = int(dff["data_inst_re"].notna().sum()) if "data_inst_re" in dff else 0
        with prog_cols[i]:
            pct_ri = ri_ok / total * 100 if total > 0 else 0
            pct_re = re_ok / total * 100 if total > 0 else 0
            st.markdown(
                f"""<div style="background:white;border-radius:10px;padding:.9rem 1rem;
                border-left:4px solid {FASE_CORES.get(fase,TEAL)};
                box-shadow:0 1px 6px rgba(0,0,0,.07);margin-bottom:.4rem;">
                <div style="font-size:.65rem;font-weight:700;text-transform:uppercase;
                letter-spacing:.05em;color:{SLATE};margin-bottom:.5rem;">
                {FASE_LABELS.get(fase,fase)} · {total:,} escolas</div>
                <div style="font-size:.78rem;color:{DARK};font-weight:600">RI instalada</div>
                <div style="background:#e2e8f0;border-radius:4px;height:8px;margin:.25rem 0 .4rem;">
                <div style="background:{FASE_CORES.get(fase,TEAL)};width:{pct_ri:.0f}%;
                height:8px;border-radius:4px;"></div></div>
                <div style="font-size:.78rem;color:{DARK};font-weight:600">RE instalada</div>
                <div style="background:#e2e8f0;border-radius:4px;height:8px;margin:.25rem 0 .4rem;">
                <div style="background:{ACCENT};width:{pct_re:.0f}%;height:8px;border-radius:4px;">
                </div></div>
                <div style="font-size:.72rem;color:{SLATE};">
                RI {ri_ok:,} ({pct_ri:.0f}%) · RE {re_ok:,} ({pct_re:.0f}%)
                </div></div>""",
                unsafe_allow_html=True,
            )

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 2 — REDE EXTERNA
# ═══════════════════════════════════════════════════════════════════════════════
with tab_re:
    col_c, col_d = st.columns(2)

    # ── Concentração de Fornecedores RE ───────────────────────────────────────
    with col_c:
        df_forn = (
            df[df["fornecedor_re"].notna() & (df["fornecedor_re"] != "")]
            .groupby("fornecedor_re")
            .size()
            .reset_index(name="contratos")
            .sort_values("contratos", ascending=False)
        )
        top_n = 8
        top   = df_forn.head(top_n).copy()
        resto = df_forn.iloc[top_n:]
        if len(resto) > 0:
            demais = pd.DataFrame({"fornecedor_re": [f"Demais ({len(resto)} fornecedores)"],
                                   "contratos": [resto["contratos"].sum()]})
            top = pd.concat([top, demais], ignore_index=True)
        top = top.sort_values("contratos")  # ascending p/ horizontal

        cores_bar = [SLATE if "Demais" in str(r["fornecedor_re"]) else TEAL
                     for _, r in top.iterrows()]
        fig_forn = go.Figure(go.Bar(
            y=top["fornecedor_re"],
            x=top["contratos"],
            orientation="h",
            marker_color=cores_bar,
            text=top["contratos"].astype(int),
            textposition="outside",
            textfont=dict(size=10),
        ))
        base_layout(fig_forn, "Contratos de RE por Fornecedor (Top 8 + Demais)",
                    height=400, showlegend=False)
        fig_forn.update_xaxes(showgrid=True, gridcolor="#f0f4f8")
        fig_forn.update_yaxes(showgrid=False, showline=False)
        st.plotly_chart(fig_forn, use_container_width=True)

    # ── Target vs. Real — Fase 4.2 ────────────────────────────────────────────
    with col_d:
        df_42 = df[
            (df["fase"] == "4.2") &
            (df["custo_mensal_re_orc"] > 0) &
            (df["custo_mensal_re_real"] > 0)
        ]
        if df_42.empty:
            st.info("Sem dados de custo RE orçado × real para Fase 4.2.")
        else:
            df_tv = (
                df_42.groupby("uf")
                .agg(target=("custo_mensal_re_orc", "mean"),
                     real=("custo_mensal_re_real", "mean"))
                .reset_index()
                .sort_values("target", ascending=False)
            )
            fig_tv = go.Figure()
            fig_tv.add_bar(name="Target orçado", x=df_tv["uf"], y=df_tv["target"],
                           marker_color=SLATE, text=df_tv["target"].round(0).astype(int),
                           textposition="outside", textfont=dict(size=9))
            fig_tv.add_bar(name="Real contratado", x=df_tv["uf"], y=df_tv["real"],
                           marker_color=TEAL, text=df_tv["real"].round(0).astype(int),
                           textposition="outside", textfont=dict(size=9))
            fig_tv.update_layout(barmode="group")
            base_layout(fig_tv, "Target vs. Real — RE Mensal Fase 4.2 (R$/escola)", height=400)
            fig_tv.update_yaxes(tickprefix="R$ ")
            st.plotly_chart(fig_tv, use_container_width=True)

    # ── Impacto Financeiro por UF — RE 24 meses ───────────────────────────────
    st.markdown("#### Impacto financeiro de RE em 24 meses (Real − Orçado por UF)")

    df_imp = df[
        (df["custo_24m_re_real"] > 0) &
        (df["custo_24m_re_orc"] > 0)
    ].copy()
    df_imp["delta"] = df_imp["custo_24m_re_real"] - df_imp["custo_24m_re_orc"]

    df_imp_uf = (
        df_imp.groupby(["uf", "fase"])["delta"]
        .sum()
        .reset_index()
        .sort_values("delta", ascending=False)
    )

    if df_imp_uf.empty:
        st.info("Sem dados de impacto financeiro com os filtros atuais.")
    else:
        df_imp_uf["cor"]    = df_imp_uf["delta"].apply(lambda v: ROJO if v > 0 else VERDE)
        df_imp_uf["tipo"]   = df_imp_uf["delta"].apply(lambda v: "Sobre-custo" if v > 0 else "Economia")
        df_imp_uf["label_uf"] = df_imp_uf["uf"] + " · " + df_imp_uf["fase"]
        df_imp_uf = df_imp_uf.sort_values("delta", ascending=True)

        fig_imp = go.Figure()
        for tipo, cor in [("Sobre-custo", ROJO), ("Economia", VERDE)]:
            sub = df_imp_uf[df_imp_uf["tipo"] == tipo]
            fig_imp.add_bar(
                name=tipo,
                y=sub["label_uf"],
                x=sub["delta"],
                orientation="h",
                marker_color=cor,
                text=sub["delta"].apply(lambda v: brl(abs(v), milhoes=True)),
                textposition="outside",
                textfont=dict(size=9),
            )

        total_econ   = df_imp_uf[df_imp_uf["delta"] < 0]["delta"].sum()
        total_sobre  = df_imp_uf[df_imp_uf["delta"] > 0]["delta"].sum()
        net          = total_econ + total_sobre

        ic1, ic2, ic3 = st.columns(3)
        ic1.metric("Sobre-custo total 24M", brl(total_sobre, milhoes=True))
        ic2.metric("Economia total 24M",    brl(abs(total_econ), milhoes=True))
        ic3.metric("Impacto líquido 24M",   brl(abs(net), milhoes=True),
                   delta=("▼ economia" if net < 0 else "▲ sobre-custo"),
                   delta_color=("normal" if net < 0 else "inverse"))

        base_layout(fig_imp, "Impacto Financeiro de RE por UF × Fase (R$, 24 meses)",
                    height=max(340, len(df_imp_uf) * 22 + 60), showlegend=True)
        fig_imp.update_xaxes(tickprefix="R$ ", zeroline=True, zerolinecolor="#e2e8f0",
                              zerolinewidth=2)
        fig_imp.update_yaxes(showgrid=False)
        st.plotly_chart(fig_imp, use_container_width=True)

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 3 — REDE INTERNA
# ═══════════════════════════════════════════════════════════════════════════════
with tab_ri:
    col_e, col_f = st.columns(2)

    # ── Custo médio de instalação por AP ─────────────────────────────────────
    with col_e:
        df_ri_custo = (
            df[df["aps_ad_impl"] > 0]
            .groupby("fase")
            .agg(custo=("custo_serv_ri", "sum"), aps=("aps_ad_impl", "sum"))
            .reset_index()
        )
        df_ri_custo["custo_por_ap"] = (df_ri_custo["custo"] / df_ri_custo["aps"]).round(2)
        df_ri_custo = df_ri_custo[df_ri_custo["fase"].isin(FASE_ORDER)]
        df_ri_custo["ordem"] = df_ri_custo["fase"].map(
            {f: i for i, f in enumerate(FASE_ORDER)})
        df_ri_custo = df_ri_custo.sort_values("ordem")
        df_ri_custo["label"] = df_ri_custo["fase"].map(lambda f: FASE_LABELS.get(f, f))

        fig_ap = go.Figure(go.Bar(
            x=df_ri_custo["label"],
            y=df_ri_custo["custo_por_ap"],
            marker_color=[FASE_CORES.get(f, TEAL) for f in df_ri_custo["fase"]],
            text=["R$ " + f"{v:,.0f}".replace(",", "X").replace(".", ",").replace("X", ".")
                  for v in df_ri_custo["custo_por_ap"]],
            textposition="outside",
            textfont=dict(size=11),
        ))
        base_layout(fig_ap, "Custo Médio de Instalação de RI por AP", height=380, showlegend=False)
        fig_ap.update_yaxes(tickprefix="R$ ")

        if len(df_ri_custo) >= 2:
            v0 = df_ri_custo["custo_por_ap"].iloc[0]
            vl = df_ri_custo["custo_por_ap"].iloc[-1]
            delta_pct = (vl - v0) / v0 * 100 if v0 > 0 else 0
            fig_ap.add_annotation(
                text=f"Variação {FASE_LABELS.get(df_ri_custo['fase'].iloc[0],'4.1')} → "
                     f"{FASE_LABELS.get(df_ri_custo['fase'].iloc[-1],'5.0')}: "
                     f"{delta_pct:+.0f}%",
                xref="paper", yref="paper", x=0.5, y=-0.1,
                showarrow=False, font=dict(size=10, color=SLATE), xanchor="center",
            )
        st.plotly_chart(fig_ap, use_container_width=True)

    # ── Scatter: Média de AP's × Cabo por AP ─────────────────────────────────
    with col_f:
        sc_rows = []
        for label, vals in SCATTER.items():
            fase_key = next(
                (f for f in FASE_ORDER if f in label.replace("Adicional", "ADICIONAL")),
                None,
            )
            sc_rows.append({
                "Fase": label,
                "Avg APs por escola": vals["aps"],
                "Cabo por AP (m)":    vals["cabo_por_ap"],
                "Escolas":            vals["escolas"],
                "cor":                FASE_CORES.get(fase_key, TEAL),
            })
        df_sc = pd.DataFrame(sc_rows)

        fig_sc = go.Figure()
        for _, row in df_sc.iterrows():
            fig_sc.add_scatter(
                x=[row["Avg APs por escola"]],
                y=[row["Cabo por AP (m)"]],
                mode="markers+text",
                name=row["Fase"],
                marker=dict(size=row["Escolas"] / 35, color=row["cor"],
                            line=dict(width=1.5, color="white"),
                            sizemode="area", sizemin=12),
                text=[row["Fase"]],
                textposition="top center",
                textfont=dict(size=9, family="Segoe UI"),
            )
        base_layout(fig_sc, "Média de AP's Instalados × Cabo Consumido por AP (m)", height=380)
        fig_sc.update_xaxes(title_text="Média de AP's por escola", range=[2.5, 8])
        fig_sc.update_yaxes(title_text="Cabo consumido por AP (m)", range=[18, 50])
        fig_sc.add_annotation(
            text="Tamanho do círculo proporcional ao nº de escolas · Fonte: TABELA FINANCEIRA 17/08/2026",
            xref="paper", yref="paper", x=0.5, y=-0.1,
            showarrow=False, font=dict(size=9, color=SLATE), xanchor="center",
        )
        st.plotly_chart(fig_sc, use_container_width=True)

    # ── Receita e Custo médio por AP ──────────────────────────────────────────
    st.markdown("#### Receita e custo médio por AP instalado — por fase")
    df_kpi_ap = (
        df[df["aps_ad_impl"] > 0]
        .groupby("fase")
        .agg(
            rec_serv=("rec_serv_ri_real", "sum"),
            rec_equip=("rec_equip_ri_real", "sum"),
            custo_serv=("custo_serv_ri", "sum"),
            custo_equip=("custo_equip_cmv", "sum"),
            aps=("aps_ad_impl", "sum"),
        )
        .reset_index()
    )
    df_kpi_ap["rec_por_ap"]  = (df_kpi_ap["rec_serv"] + df_kpi_ap["rec_equip"]) / df_kpi_ap["aps"]
    df_kpi_ap["custo_por_ap"] = (df_kpi_ap["custo_serv"] + df_kpi_ap["custo_equip"]) / df_kpi_ap["aps"]
    df_kpi_ap["margem_por_ap"] = df_kpi_ap["rec_por_ap"] - df_kpi_ap["custo_por_ap"]
    df_kpi_ap = df_kpi_ap[df_kpi_ap["fase"].isin(FASE_ORDER)]

    fig_rc = go.Figure()
    df_kpi_ap = df_kpi_ap.sort_values("fase")
    labels_ap = df_kpi_ap["fase"].map(lambda f: FASE_LABELS.get(f, f))
    fig_rc.add_bar(name="Receita/AP", x=labels_ap, y=df_kpi_ap["rec_por_ap"],
                   marker_color=ACCENT, text=df_kpi_ap["rec_por_ap"].round(0).astype(int),
                   textposition="outside", textfont=dict(size=10))
    fig_rc.add_bar(name="Custo/AP", x=labels_ap, y=df_kpi_ap["custo_por_ap"],
                   marker_color=TEAL, text=df_kpi_ap["custo_por_ap"].round(0).astype(int),
                   textposition="outside", textfont=dict(size=10))
    fig_rc.update_layout(barmode="group")
    base_layout(fig_rc, "Receita e Custo Médio por AP Instalado (R$)", height=340)
    fig_rc.update_yaxes(tickprefix="R$ ")
    fig_rc.update_traces(textposition="outside", textfont_size=10)
    fig_rc.update_layout(uniformtext_minsize=9, uniformtext_mode="hide",
                          xaxis_type="category")
    st.plotly_chart(fig_rc, use_container_width=True)

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 4 — LOGÍSTICA
# ═══════════════════════════════════════════════════════════════════════════════
with tab_log:
    col_g, col_h = st.columns(2)

    # ── Contratações de transporte ────────────────────────────────────────────
    with col_g:
        df_tr = (
            pd.DataFrame(list(TRANSPORTES.items()), columns=["Transportadora", "Contratações"])
            .sort_values("Contratações")
        )
        total_tr = df_tr["Contratações"].sum()
        cores_tr = [TEAL if v >= 10 else (ACCENT if v >= 4 else SLATE)
                    for v in df_tr["Contratações"]]
        fig_tr = go.Figure(go.Bar(
            y=df_tr["Transportadora"],
            x=df_tr["Contratações"],
            orientation="h",
            marker_color=cores_tr,
            text=df_tr["Contratações"].astype(int),
            textposition="outside",
            textfont=dict(size=10),
        ))
        base_layout(fig_tr,
                    f"Contratações de Transporte por Transportadora 2026 (Total: {total_tr})",
                    height=420, showlegend=False)
        fig_tr.update_xaxes(showgrid=True)
        fig_tr.update_yaxes(showgrid=False)
        fig_tr.add_annotation(
            text="Fonte: TABELA FINANCEIRA · 17/08/2026",
            xref="paper", yref="paper", x=1, y=-0.08,
            showarrow=False, font=dict(size=9, color=SLATE), xanchor="right",
        )
        st.plotly_chart(fig_tr, use_container_width=True)

    # ── Valor por transportadora ──────────────────────────────────────────────
    with col_h:
        VALORES_TR = {
            "FLEX CARGO LTDA ME":           232_011,
            "EAGLE SOLUÇÕES LOGÍSTICAS":     67_054,
            "LOGGO SOLUÇÕES LOGÍSTICAS":     55_502,
            "FLEX CARGO LTDA":              39_698,
            "BRASPRESS TRANSPORTES":         12_407,
            "A. R. T. TÁXI AÉREO":          23_000,
            "BRINGER DO BRASIL":             1_276,
            "L4B LOGÍSTICA LTDA":              226,
            "GUERINO SEISCENTO":               130,
            "UNIAO TRANSPORTE DE ENCOM.":    1_850,
            "VITA AIR CARGO":                    0,
            "RODOVIÁRIO CAMILO DOS SANTOS":    428,
        }
        df_vtr = (
            pd.DataFrame(list(VALORES_TR.items()), columns=["Transportadora", "Valor"])
            .sort_values("Valor")
        )
        fig_vtr = go.Figure(go.Bar(
            y=df_vtr["Transportadora"],
            x=df_vtr["Valor"],
            orientation="h",
            marker_color=TEAL,
            text=[brl(v) for v in df_vtr["Valor"]],
            textposition="outside",
            textfont=dict(size=9),
        ))
        base_layout(fig_vtr, f"Valor Total por Transportadora 2026 (R$ {433_582:,.0f})".replace(",", "."),
                    height=420, showlegend=False)
        fig_vtr.update_xaxes(tickprefix="R$ ", tickformat=".0f")
        fig_vtr.update_yaxes(showgrid=False)
        st.plotly_chart(fig_vtr, use_container_width=True)

    # ── Custo RE Instaladas 24M por fase (da tabela) ──────────────────────────
    st.markdown("---")
    st.markdown("#### Síntese financeira de RE em 24 meses")

    fin_re = (
        df[df["rec_mens_re_24m"] > 0]
        .groupby("fase")
        .agg(
            receita_24m=("rec_mens_re_24m", "sum"),
            custo_24m=("custo_24m_re_real", "sum"),
            custo_orc=("custo_24m_re_orc", "sum"),
            escolas=("inep", "count"),
        )
        .reset_index()
        .sort_values("fase")
    )
    fin_re["margem_24m"] = fin_re["receita_24m"] - fin_re["custo_24m"]
    fin_re["label"] = fin_re["fase"].map(lambda f: FASE_LABELS.get(f, f))

    if not fin_re.empty:
        fc1, fc2, fc3 = st.columns(3)
        fig_r24 = go.Figure()
        fig_r24.add_bar(name="Receita 24M", x=fin_re["label"], y=fin_re["receita_24m"],
                        marker_color=ACCENT)
        fig_r24.add_bar(name="Custo Real 24M", x=fin_re["label"], y=fin_re["custo_24m"],
                        marker_color=TEAL)
        fig_r24.add_bar(name="Custo Orç. 24M", x=fin_re["label"], y=fin_re["custo_orc"],
                        marker_color=SLATE)
        fig_r24.update_layout(barmode="group")
        base_layout(fig_r24, "Receita × Custo de RE 24 Meses (R$)", height=320)
        fig_r24.update_yaxes(tickformat=".2s", tickprefix="R$ ")
        st.plotly_chart(fig_r24, use_container_width=True)

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 2 — continuação: ANÁLISE DE REDUÇÃO DE CUSTOS RE
# ═══════════════════════════════════════════════════════════════════════════════
with tab_re:
    st.markdown("---")
    st.markdown("### 📊 Análise de Custos de Mensalidade RE — GERAL COMPRA 4.2")
    st.caption("Base: Custo Mensalidade Real (Coluna T) · Fase 4.2 · Fonte: PLANILHA GERAL DE COMPRAS")

    df_re = carregar_dados_re_supabase()

    if df_re.empty:
        st.warning("Planilha GERAL COMPRA 4.2 não encontrada ou sem dados.")
    else:
        # ── Filtros específicos da análise RE ─────────────────────────────────
        with st.expander("🔽 Filtros da análise", expanded=True):
            fa1, fa2, fa3, fa4 = st.columns(4)
            with fa1:
                ufs_re_disp = sorted(df_re["uf"].unique())
                ufs_re_sel  = st.multiselect("UF", ufs_re_disp, default=ufs_re_disp, key="re_uf")
            with fa2:
                clfs_disp = sorted(df_re[df_re["classificacao"] != ""]["classificacao"].unique())
                clfs_sel  = st.multiselect("Classificação", clfs_disp, default=clfs_disp, key="re_clf")
            with fa3:
                locs_disp = sorted(df_re["localizacao"].unique())
                locs_sel  = st.multiselect("Localização", locs_disp, default=locs_disp, key="re_loc")
            with fa4:
                VEL_ORDER = ["≤50 Mbps", "51-100 Mbps", "101-200 Mbps", "201-500 Mbps", ">500 Mbps"]
                faixas_disp = [v for v in VEL_ORDER if v in df_re["vel_faixa"].unique()]
                faixas_sel  = st.multiselect("Faixa de Velocidade", faixas_disp, default=faixas_disp, key="re_vel")

        df_rf = df_re[
            df_re["uf"].isin(ufs_re_sel) &
            df_re["classificacao"].isin(clfs_sel) &
            df_re["localizacao"].isin(locs_sel) &
            df_re["vel_faixa"].isin(faixas_sel)
        ].copy()

        total_linhas = len(df_rf)
        media_geral  = df_rf["mensalidade"].mean() if total_linhas > 0 else 0
        mediana_geral = df_rf["mensalidade"].median() if total_linhas > 0 else 0

        kre1, kre2, kre3, kre4 = st.columns(4)
        kre1.metric("Contratos selecionados", f"{total_linhas:,}".replace(",", "."))
        kre2.metric("Mensalidade Média", brl(media_geral))
        kre3.metric("Mensalidade Mediana", brl(mediana_geral))
        kre4.metric("Custo Total 24M", brl(df_rf["custo_24m"].sum(), milhoes=True))

        st.markdown("---")

        # ── ROW 1: Média por UF + Média por Classificação ────────────────────
        r1c1, r1c2 = st.columns(2)

        with r1c1:
            df_uf = (
                df_rf.groupby("uf")
                .agg(media=("mensalidade", "mean"), count=("mensalidade", "count"))
                .reset_index()
                .sort_values("media", ascending=True)
            )
            fig_uf = go.Figure(go.Bar(
                y=df_uf["uf"],
                x=df_uf["media"],
                orientation="h",
                marker_color=[
                    ROJO if v > media_geral * 1.1 else (VERDE if v < media_geral * 0.9 else TEAL)
                    for v in df_uf["media"]
                ],
                text=[f"R$ {v:,.0f}  ({n} escolas)".replace(",", ".") for v, n in zip(df_uf["media"], df_uf["count"])],
                textposition="outside",
                textfont=dict(size=9),
            ))
            fig_uf.add_vline(x=media_geral, line_dash="dash", line_color=SLATE,
                             annotation_text=f"Média geral: {brl(media_geral)}",
                             annotation_position="top right",
                             annotation_font_size=9)
            base_layout(fig_uf, "Mensalidade Média por UF (R$)", height=max(380, len(df_uf)*24+60), showlegend=False)
            fig_uf.update_xaxes(tickprefix="R$ ", showgrid=True)
            fig_uf.update_yaxes(showgrid=False)
            st.plotly_chart(fig_uf, use_container_width=True)

        with r1c2:
            df_clf = (
                df_rf[df_rf["classificacao"] != ""]
                .groupby("classificacao")
                .agg(media=("mensalidade", "mean"), count=("mensalidade", "count"))
                .reset_index()
                .sort_values("media", ascending=False)
            )
            CORES_CLF = {"Broker": TEAL, "Provedor": ACCENT, "Operadora": AZUL}
            fig_clf = go.Figure(go.Bar(
                x=df_clf["classificacao"],
                y=df_clf["media"],
                marker_color=[CORES_CLF.get(c, SLATE) for c in df_clf["classificacao"]],
                text=[f"R$ {v:,.0f}<br>({n} contratos)".replace(",", ".") for v, n in zip(df_clf["media"], df_clf["count"])],
                textposition="outside",
                textfont=dict(size=11),
            ))
            fig_clf.add_hline(y=media_geral, line_dash="dash", line_color=SLATE,
                              annotation_text=f"Média geral: {brl(media_geral)}",
                              annotation_position="top right", annotation_font_size=9)
            base_layout(fig_clf, "Mensalidade Média por Classificação do Fornecedor (R$)",
                        height=380, showlegend=False)
            fig_clf.update_yaxes(tickprefix="R$ ")
            st.plotly_chart(fig_clf, use_container_width=True)

        # ── ROW 2: Média por Velocidade + Média por Localização ───────────────
        r2c1, r2c2 = st.columns(2)

        with r2c1:
            df_vel = (
                df_rf.groupby("vel_faixa")
                .agg(media=("mensalidade", "mean"), count=("mensalidade", "count"),
                     mediana=("mensalidade", "median"))
                .reset_index()
            )
            df_vel["ordem"] = df_vel["vel_faixa"].map(
                {v: i for i, v in enumerate(VEL_ORDER)})
            df_vel = df_vel.sort_values("ordem")

            fig_vel = go.Figure()
            fig_vel.add_bar(
                name="Média",
                x=df_vel["vel_faixa"],
                y=df_vel["media"],
                marker_color=TEAL,
                text=[f"R$ {v:,.0f}".replace(",", ".") for v in df_vel["media"]],
                textposition="outside",
                textfont=dict(size=10),
            )
            fig_vel.add_scatter(
                name="Mediana",
                x=df_vel["vel_faixa"],
                y=df_vel["mediana"],
                mode="markers+lines",
                marker=dict(size=10, color=ACCENT, line=dict(width=2, color="white")),
                line=dict(color=ACCENT, width=2, dash="dot"),
            )
            # Anotação com nº de contratos
            for _, row_v in df_vel.iterrows():
                fig_vel.add_annotation(
                    x=row_v["vel_faixa"], y=0,
                    text=f"{row_v['count']} contratos",
                    showarrow=False,
                    font=dict(size=8, color=SLATE),
                    yshift=-18, xanchor="center",
                )
            base_layout(fig_vel, "Mensalidade Média e Mediana por Faixa de Velocidade (R$)", height=380)
            fig_vel.update_yaxes(tickprefix="R$ ")
            st.plotly_chart(fig_vel, use_container_width=True)

        with r2c2:
            df_loc = (
                df_rf[df_rf["localizacao"].isin(["RURAL", "URBANA"])]
                .groupby("localizacao")
                .agg(media=("mensalidade", "mean"), count=("mensalidade", "count"),
                     total_24m=("custo_24m", "sum"))
                .reset_index()
            )
            CORES_LOC = {"RURAL": "#D97706", "URBANA": AZUL}
            fig_loc = go.Figure(go.Bar(
                x=df_loc["localizacao"],
                y=df_loc["media"],
                marker_color=[CORES_LOC.get(l, SLATE) for l in df_loc["localizacao"]],
                text=[f"R$ {v:,.0f}<br>({n} escolas)".replace(",", ".") for v, n in zip(df_loc["media"], df_loc["count"])],
                textposition="outside",
                textfont=dict(size=12),
            ))
            if len(df_loc) == 2:
                v_rural = df_loc[df_loc["localizacao"] == "RURAL"]["media"].values
                v_urban = df_loc[df_loc["localizacao"] == "URBANA"]["media"].values
                if len(v_rural) and len(v_urban):
                    premium = (v_rural[0] - v_urban[0]) / v_urban[0] * 100
                    fig_loc.add_annotation(
                        text=f"Premium Rural: +{premium:.1f}%" if premium > 0 else f"Rural: {premium:.1f}% vs Urbana",
                        xref="paper", yref="paper", x=0.5, y=1.12,
                        showarrow=False,
                        font=dict(size=12, color="#D97706" if premium > 0 else VERDE, family="Segoe UI"),
                        xanchor="center",
                    )
            base_layout(fig_loc, "Mensalidade Média por Localização (R$)", height=380, showlegend=False)
            fig_loc.update_yaxes(tickprefix="R$ ")
            st.plotly_chart(fig_loc, use_container_width=True)

        # ── ROW 3: Cruzamento Velocidade × Localização (premium rural por banda) ──
        st.markdown("#### Custo médio por banda e localização — rural vs. urbana")
        st.caption("Mostra se o alegado sobre-custo rural é consistente em todas as velocidades.")

        df_cross = (
            df_rf[df_rf["localizacao"].isin(["RURAL", "URBANA"])]
            .groupby(["vel_faixa", "localizacao"])
            .agg(media=("mensalidade", "mean"), count=("mensalidade", "count"))
            .reset_index()
        )
        df_cross["ordem"] = df_cross["vel_faixa"].map({v: i for i, v in enumerate(VEL_ORDER)})
        df_cross = df_cross.sort_values("ordem")

        fig_cross = go.Figure()
        for loc, cor in [("RURAL", "#D97706"), ("URBANA", AZUL)]:
            sub = df_cross[df_cross["localizacao"] == loc]
            fig_cross.add_bar(
                name=loc.title(),
                x=sub["vel_faixa"],
                y=sub["media"],
                marker_color=cor,
                text=[f"R$ {v:,.0f}".replace(",", ".") for v in sub["media"]],
                textposition="outside",
                textfont=dict(size=9),
            )
        fig_cross.update_layout(barmode="group")
        base_layout(fig_cross, "Mensalidade Média: Rural vs. Urbana por Faixa de Velocidade", height=360)
        fig_cross.update_yaxes(tickprefix="R$ ")
        st.plotly_chart(fig_cross, use_container_width=True)

        # ── ROW 4: Custo por Classificação × Velocidade ─────────────────────
        st.markdown("#### Custo médio por fornecedor × velocidade")
        df_clf_vel = (
            df_rf[df_rf["classificacao"] != ""]
            .groupby(["vel_faixa", "classificacao"])
            .agg(media=("mensalidade", "mean"), count=("mensalidade", "count"))
            .reset_index()
        )
        df_clf_vel["ordem"] = df_clf_vel["vel_faixa"].map({v: i for i, v in enumerate(VEL_ORDER)})
        df_clf_vel = df_clf_vel.sort_values("ordem")

        fig_cv = go.Figure()
        for cls, cor in [("Broker", TEAL), ("Provedor", ACCENT), ("Operadora", AZUL)]:
            sub = df_clf_vel[df_clf_vel["classificacao"] == cls]
            if not sub.empty:
                fig_cv.add_bar(
                    name=cls,
                    x=sub["vel_faixa"],
                    y=sub["media"],
                    marker_color=cor,
                    text=[f"R$ {v:,.0f}".replace(",", ".") for v in sub["media"]],
                    textposition="outside",
                    textfont=dict(size=9),
                )
        fig_cv.update_layout(barmode="group")
        base_layout(fig_cv, "Mensalidade Média por Classificação × Faixa de Velocidade", height=360)
        fig_cv.update_yaxes(tickprefix="R$ ")
        st.plotly_chart(fig_cv, use_container_width=True)

        # ── Exportar dados detalhados ──────────────────────────────────────────
        st.markdown("---")
        st.markdown("**Exportar dados filtrados:**")

        df_export = df_rf[["fase","uf","municipio","velocidade","vel_faixa","classificacao",
                            "fornecedor","mensalidade","instalacao","custo_24m","localizacao"]].copy()
        df_export.columns = ["Fase","UF","Município","Velocidade (Mbps)","Faixa Velocidade",
                              "Classificação","Fornecedor","Mensalidade Real (R$)",
                              "Instalação Real (R$)","Custo 24M (R$)","Localização"]

        csv_re = df_export.to_csv(index=False).encode("utf-8")
        st.download_button(
            "⬇️ Exportar análise de custos RE (.csv)",
            data=csv_re,
            file_name="analise_custos_RE_mensalidade.csv",
            mime="text/csv",
            use_container_width=True,
        )
