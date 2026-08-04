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

FASES = ["4.1", "4.2", "4.2 ADICIONAL", "5.0", "SATÉLITE"]

@st.cache_data(ttl=600)
def carregar_ufs_disponiveis():
    """Retorna lista de UFs presentes nas execuções."""
    rows, offset = [], 0
    while True:
        r = sb.table("execucoes").select("uf").range(offset, offset + 999).execute()
        rows.extend(r.data)
        if len(r.data) < 1000: break
        offset += 1000
    ufs = sorted({(row.get("uf") or "").strip().upper() for row in rows if row.get("uf")})
    return ufs

@st.cache_data(ttl=30)
def carregar_uf_parceiros():
    """Retorna {parceiro_id: UF_principal} derivado das execuções reais."""
    rp = sb.table("parceiros").select("id, uf").execute().data
    id_to_uf = {p["id"]: (p.get("uf") or "") for p in rp}
    exec_rows, offset = [], 0
    while True:
        r = sb.table("execucoes").select("uf, parceiro_id").range(offset, offset + 999).execute()
        exec_rows.extend(r.data)
        if len(r.data) < 1000: break
        offset += 1000
    # UF mais frequente por parceiro via execuções
    from collections import Counter
    freq: dict = {}
    for row in exec_rows:
        pid = row.get("parceiro_id")
        uf  = (row.get("uf") or "").strip().upper()
        if pid and uf:
            freq.setdefault(pid, Counter())[uf] += 1
    for pid, counter in freq.items():
        id_to_uf[pid] = counter.most_common(1)[0][0]
    return id_to_uf

@st.cache_data(ttl=30)
def carregar_transferencias():
    # Usa select("*") para pegar uf_origem/uf_destino se já existirem na tabela
    r = (sb.table("transferencias")
         .select("*")
         .order("id", desc=True)
         .execute())
    rp = sb.table("parceiros").select("id, nome").execute()
    ri = sb.table("itens").select("id, nome").execute()
    parc_map = {p["id"]: p["nome"] for p in rp.data}
    item_map = {i["id"]: i["nome"] for i in ri.data}
    uf_map   = carregar_uf_parceiros()   # fallback para registros sem UF

    rows = []
    for t in r.data:
        fo  = t.get("fase_origem") or t.get("fase") or ""
        fd  = t.get("fase_destino") or t.get("fase") or ""
        ufo = t.get("uf_origem") or uf_map.get(t.get("parceiro_origem_id"), "")
        ufd = t.get("uf_destino") or uf_map.get(t.get("parceiro_destino_id"), "")
        rows.append({
            "ID":           t["id"],
            "Origem":       parc_map.get(t["parceiro_origem_id"], ""),
            "UF Origem":    ufo,
            "Fase Origem":  fo,
            "Destino":      parc_map.get(t["parceiro_destino_id"], ""),
            "UF Destino":   ufd,
            "Fase Destino": fd,
            "Item":         item_map.get(t["item_id"], ""),
            "Qtd":          t["qtd"],
            "Motivo":       t["motivo"] or "",
            "Data":         t["data_transferencia"] or "",
            "Status":       t["status"] or "",
            "Data Aceite":  t["data_aceite"] or "",
        })
    colunas = ["ID","Origem","UF Origem","Fase Origem","Destino","UF Destino","Fase Destino",
               "Item","Qtd","Motivo","Data","Status","Data Aceite"]
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
    ufs_disp = carregar_ufs_disponiveis()

    with st.form("form_transf", clear_on_submit=True):
        # ── Origem ────────────────────────────────────────────────────────────
        st.markdown("**Origem**")
        col1, col2, col_ufo = st.columns([3, 2, 1])
        with col1:
            origem_sel  = st.selectbox("Parceiro de Origem *", nomes_parceiros, key="orig_parc")
        with col2:
            fase_origem = st.selectbox("Fase de Origem *", FASES, key="orig_fase")
        with col_ufo:
            uf_origem   = st.selectbox("UF Origem", ufs_disp, key="orig_uf")

        st.markdown("**Destino**")
        col3, col4, col_ufd = st.columns([3, 2, 1])
        with col3:
            destino_sel = st.selectbox("Parceiro de Destino *", nomes_parceiros, key="dest_parc")
        with col4:
            fase_destino = st.selectbox("Fase de Destino *", FASES, key="dest_fase")
        with col_ufd:
            uf_destino  = st.selectbox("UF Destino", ufs_disp, key="dest_uf")

        # ── Item / Qtd / Data ─────────────────────────────────────────────────
        st.markdown("**Material**")
        col5, col6, col7 = st.columns([3, 1, 1])
        with col5:
            item_sel = st.selectbox("Item *", list(itens_dict.keys()))
        with col6:
            qtd = st.number_input("Quantidade *", min_value=1, value=1)
        with col7:
            data_transf = st.date_input("Data", value=date.today())

        motivo = st.text_input("Motivo / Observação")
        submitted = st.form_submit_button("📤 Registrar Transferência", use_container_width=True, type="primary")

    if submitted:
        mesma_origem = (origem_sel == destino_sel and fase_origem == fase_destino)
        if mesma_origem:
            st.error("Origem e destino não podem ser o mesmo parceiro + fase.")
        else:
            payload = {
                "parceiro_origem_id":  parceiros[origem_sel],
                "parceiro_destino_id": parceiros[destino_sel],
                "item_id":             itens_dict[item_sel],
                "qtd":                 int(qtd),
                "fase":                fase_origem,
                "fase_origem":         fase_origem,
                "fase_destino":        fase_destino,
                "uf_origem":           uf_origem or None,
                "uf_destino":          uf_destino or None,
                "motivo":              motivo or None,
                "data_transferencia":  str(data_transf),
                "status":              "pendente",
            }
            try:
                sb.table("transferencias").insert(payload).execute()
            except Exception as e:
                if "uf_origem" in str(e) or "uf_destino" in str(e):
                    # Colunas ainda não existem no banco — insere sem elas
                    payload.pop("uf_origem", None)
                    payload.pop("uf_destino", None)
                    try:
                        sb.table("transferencias").insert(payload).execute()
                    except Exception as e2:
                        st.error(f"Erro ao registrar: {e2}")
                        st.stop()
                else:
                    st.error(f"Erro ao registrar: {e}")
                    st.stop()
            destino_label = f"**{destino_sel}** (fase {fase_destino})"
            if fase_origem != fase_destino:
                destino_label += f" — transferência entre fases ({fase_origem} → {fase_destino})"
            st.success(f"✅ Transferência registrada! Aguardando confirmação de {destino_label}.")
            st.cache_data.clear()
            st.rerun()

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
            df_pend[["ID","Origem","UF Origem","Fase Origem","Destino","UF Destino","Fase Destino","Item","Qtd","Motivo","Data"]],
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

    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        parc_f = st.selectbox("Parceiro", ["Todos"] + sorted(
            set(df_hist["Origem"].unique().tolist() + df_hist["Destino"].unique().tolist())
        ), key="h_parc")
    with col2:
        fases_hist = sorted(set(
            df_hist["Fase Origem"].dropna().unique().tolist() +
            df_hist["Fase Destino"].dropna().unique().tolist()
        ))
        fase_f = st.selectbox("Fase (origem ou destino)", ["Todas"] + fases_hist, key="h_fase")
    with col3:
        all_ufs_hist = sorted(set(
            df_hist["UF Origem"].dropna().unique().tolist() +
            df_hist["UF Destino"].dropna().unique().tolist()
        ))
        uf_f = st.selectbox("UF (origem ou destino)", ["Todas"] + all_ufs_hist, key="h_uf")
    with col4:
        status_f = st.selectbox("Status", ["Todos", "aceito", "pendente", "rejeitado"], key="h_status")
    with col5:
        cross_fase = st.checkbox("Somente entre fases diferentes", key="h_cross")

    df_view = df_hist.copy()
    if parc_f != "Todos":
        df_view = df_view[(df_view["Origem"] == parc_f) | (df_view["Destino"] == parc_f)]
    if fase_f != "Todas":
        df_view = df_view[(df_view["Fase Origem"] == fase_f) | (df_view["Fase Destino"] == fase_f)]
    if uf_f != "Todas":
        df_view = df_view[(df_view["UF Origem"] == uf_f) | (df_view["UF Destino"] == uf_f)]
    if status_f != "Todos":
        df_view = df_view[df_view["Status"] == status_f]
    if cross_fase:
        df_view = df_view[df_view["Fase Origem"] != df_view["Fase Destino"]]

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
