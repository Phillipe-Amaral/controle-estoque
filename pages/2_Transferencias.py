import streamlit as st
from supabase import create_client
import pandas as pd
from datetime import date
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from utils.tema_iuh import aplicar_tema, sidebar_logo, page_header

st.set_page_config(page_title="Transferências", page_icon="🔄", layout="wide")
aplicar_tema()
sidebar_logo("Transferências")

SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]

@st.cache_resource
def get_client():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

sb = get_client()

# ── Helpers ───────────────────────────────────────────────────────────────────
@st.cache_data(ttl=30)
def carregar_parceiros():
    r = sb.table("parceiros").select("id, nome").order("nome").execute()
    return {p["nome"]: p["id"] for p in r.data}

@st.cache_data(ttl=30)
def carregar_itens():
    r = sb.table("itens").select("id, nome, fabricante").order("nome").execute()
    return r.data

@st.cache_data(ttl=30)
def carregar_transferencias():
    r = (sb.table("transferencias")
         .select("id, parceiro_origem_id, parceiro_destino_id, item_id, qtd, fase, motivo, data_transferencia, status, data_aceite")
         .order("id", desc=True)
         .execute())
    rp = sb.table("parceiros").select("id, nome").execute()
    ri = sb.table("itens").select("id, nome").execute()
    parc_map = {p["id"]: p["nome"] for p in rp.data}
    item_map = {i["id"]: i["nome"] for i in ri.data}

    colunas = ["ID","Origem","Destino","Item","Qtd","Fase","Motivo","Data","Status","Data Aceite"]
    rows = []
    for t in r.data:
        rows.append({
            "ID":         t["id"],
            "Origem":     parc_map.get(t["parceiro_origem_id"], ""),
            "Destino":    parc_map.get(t["parceiro_destino_id"], ""),
            "Item":       item_map.get(t["item_id"], ""),
            "Qtd":        t["qtd"],
            "Fase":       t["fase"] or "",
            "Motivo":     t["motivo"] or "",
            "Data":       t["data_transferencia"] or "",
            "Status":     t["status"] or "",
            "Data Aceite":t["data_aceite"] or "",
        })
    return pd.DataFrame(rows, columns=colunas) if rows else pd.DataFrame(columns=colunas)

# ── Título ────────────────────────────────────────────────────────────────────
page_header("🔄 Transferências entre Parceiros", "Registre e acompanhe movimentações de material entre parceiros")

tab1, tab2, tab3 = st.tabs(["➕ Nova Transferência", "✅ Confirmar Recebimento", "📋 Histórico"])

# ══════════════════════════════════════════════════════════════════════════════
# ABA 1 — NOVA TRANSFERÊNCIA
# ══════════════════════════════════════════════════════════════════════════════
with tab1:
    st.subheader("Registrar nova transferência")
    st.info("O parceiro de destino precisará confirmar o recebimento para que o saldo seja atualizado.")

    parceiros = carregar_parceiros()
    itens_lista = carregar_itens()
    itens_dict = {f"{i['nome']} ({i['fabricante'] or 'sem fab.'})": i["id"] for i in itens_lista}
    nomes_parceiros = list(parceiros.keys())

    with st.form("form_transf", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            origem_sel  = st.selectbox("Parceiro de Origem *", nomes_parceiros)
            item_sel    = st.selectbox("Item *", list(itens_dict.keys()))
            fase        = st.selectbox("Fase", ["4.2", "4.1", "5.0"])
        with col2:
            destinos = [p for p in nomes_parceiros if p != origem_sel]
            destino_sel = st.selectbox("Parceiro de Destino *", nomes_parceiros)
            qtd         = st.number_input("Quantidade *", min_value=1, value=1)
            data_transf = st.date_input("Data da Transferência", value=date.today())

        motivo = st.text_input("Motivo / Observação")

        submitted = st.form_submit_button("📤 Registrar Transferência", use_container_width=True, type="primary")

    if submitted:
        if origem_sel == destino_sel:
            st.error("Origem e destino não podem ser o mesmo parceiro.")
        else:
            try:
                sb.table("transferencias").insert({
                    "parceiro_origem_id":  parceiros[origem_sel],
                    "parceiro_destino_id": parceiros[destino_sel],
                    "item_id":             itens_dict[item_sel],
                    "qtd":                 int(qtd),
                    "fase":                fase,
                    "motivo":              motivo or None,
                    "data_transferencia":  str(data_transf),
                    "status":              "pendente",
                }).execute()
                st.success(f"✅ Transferência registrada! Aguardando confirmação de **{destino_sel}**.")
                st.cache_data.clear()
                st.rerun()
            except Exception as e:
                st.error(f"Erro ao registrar: {e}")

# ══════════════════════════════════════════════════════════════════════════════
# ABA 2 — CONFIRMAR RECEBIMENTO
# ══════════════════════════════════════════════════════════════════════════════
with tab2:
    st.subheader("Confirmar ou rejeitar transferências pendentes")

    df_transf = carregar_transferencias()
    df_pend = df_transf[df_transf["Status"] == "pendente"].copy()

    if df_pend.empty:
        st.success("✅ Nenhuma transferência aguardando confirmação!")
    else:
        st.warning(f"⏳ **{len(df_pend)} transferência(s) aguardando confirmação**")
        st.dataframe(
            df_pend[["ID","Origem","Destino","Item","Qtd","Fase","Motivo","Data"]],
            use_container_width=True, hide_index=True
        )

        st.markdown("---")
        st.markdown("**Registrar decisão:**")

        col1, col2, col3 = st.columns(3)
        with col1:
            id_sel = st.number_input("ID da Transferência", min_value=1, step=1)
        with col2:
            decisao = st.selectbox("Decisão", ["aceito", "rejeitado"])
        with col3:
            data_aceite = st.date_input("Data", value=date.today())

        obs = st.text_input("Observação (opcional)", key="obs_aceite")

        if st.button("✅ Confirmar Decisão", type="primary", use_container_width=True):
            try:
                update_data = {
                    "status":      decisao,
                    "data_aceite": str(data_aceite),
                }
                if obs:
                    update_data["motivo"] = obs
                sb.table("transferencias").update(update_data).eq("id", int(id_sel)).execute()
                icone = "✅" if decisao == "aceito" else "❌"
                st.success(f"{icone} Transferência #{id_sel} marcada como **{decisao}**!")
                st.cache_data.clear()
                st.rerun()
            except Exception as e:
                st.error(f"Erro: {e}")

# ══════════════════════════════════════════════════════════════════════════════
# ABA 3 — HISTÓRICO
# ══════════════════════════════════════════════════════════════════════════════
with tab3:
    st.subheader("Histórico de transferências")

    df_hist = carregar_transferencias()

    col1, col2, col3 = st.columns(3)
    with col1:
        parc_f = st.selectbox("Parceiro (origem ou destino)", ["Todos"] + sorted(
            set(df_hist["Origem"].unique().tolist() + df_hist["Destino"].unique().tolist())
        ), key="h_parc")
    with col2:
        fase_f = st.selectbox("Fase", ["Todas"] + sorted(df_hist["Fase"].dropna().unique().tolist()), key="h_fase")
    with col3:
        status_f = st.selectbox("Status", ["Todos", "aceito", "pendente", "rejeitado"], key="h_status")

    df_view = df_hist.copy()
    if parc_f != "Todos":
        df_view = df_view[(df_view["Origem"] == parc_f) | (df_view["Destino"] == parc_f)]
    if fase_f != "Todas":
        df_view = df_view[df_view["Fase"] == fase_f]
    if status_f != "Todos":
        df_view = df_view[df_view["Status"] == status_f]

    def colorir_status(val):
        if val == "aceito":     return "background-color:#d4edda; color:#155724"
        if val == "pendente":   return "background-color:#fff3cd; color:#856404"
        if val == "rejeitado":  return "background-color:#f8d7da; color:#721c24"
        return ""

    st.dataframe(
        df_view.style.map(colorir_status, subset=["Status"]),
        use_container_width=True, hide_index=True, height=500
    )

    col_a, col_b = st.columns(2)
    col_a.metric("Total de transferências", len(df_view))
    col_b.metric("Qtd total movimentada", int(df_view["Qtd"].sum()) if not df_view.empty else 0)

    st.download_button(
        "⬇️ Exportar (.csv)",
        data=df_view.to_csv(index=False).encode("utf-8"),
        file_name="historico_transferencias.csv",
        mime="text/csv",
    )
