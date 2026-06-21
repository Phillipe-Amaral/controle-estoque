import streamlit as st
from supabase import create_client
import pandas as pd
from datetime import date

st.set_page_config(page_title="Compras", page_icon="🛒", layout="wide")

# ── Conexão ───────────────────────────────────────────────────────────────────
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
def carregar_compras():
    r = (sb.table("compras")
         .select("id, parceiros(nome), itens(nome), fornecedor, qtd_pedida, qtd_recebida, valor_unitario, numero_pedido, nf, fase, data_pedido, data_recebimento")
         .order("id", desc=True)
         .execute())
    rows = []
    for c in r.data:
        rows.append({
            "ID":          c["id"],
            "Parceiro":    c["parceiros"]["nome"] if c["parceiros"] else "",
            "Item":        c["itens"]["nome"] if c["itens"] else "",
            "Fornecedor":  c["fornecedor"] or "",
            "Qtd Pedida":  c["qtd_pedida"],
            "Qtd Recebida":c["qtd_recebida"] or 0,
            "Valor Unit.": c["valor_unitario"] or 0,
            "Nº Pedido":   c["numero_pedido"] or "",
            "NF":          c["nf"] or "",
            "Fase":        c["fase"] or "",
            "Data Pedido": c["data_pedido"] or "",
            "Data Receb.": c["data_recebimento"] or "",
        })
    colunas = ["ID","Parceiro","Item","Fornecedor","Qtd Pedida","Qtd Recebida",
               "Valor Unit.","Nº Pedido","NF","Fase","Data Pedido","Data Receb."]
    return pd.DataFrame(rows, columns=colunas) if rows else pd.DataFrame(columns=colunas)

# ── Título ────────────────────────────────────────────────────────────────────
st.title("🛒 Cadastro de Compras")
st.caption("Registre novos pedidos e confirme o recebimento de mercadorias")

tab1, tab2, tab3 = st.tabs(["➕ Nova Compra", "✅ Confirmar Recebimento", "📋 Histórico"])

# ══════════════════════════════════════════════════════════════════════════════
# ABA 1 — NOVA COMPRA
# ══════════════════════════════════════════════════════════════════════════════
with tab1:
    st.subheader("Registrar novo pedido de compra")

    parceiros = carregar_parceiros()
    itens_lista = carregar_itens()
    itens_dict = {f"{i['nome']} ({i['fabricante'] or 'sem fab.'})": i["id"] for i in itens_lista}

    with st.form("form_compra", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            parceiro_sel = st.selectbox("Parceiro *", list(parceiros.keys()))
            item_sel     = st.selectbox("Item *", list(itens_dict.keys()))
            fornecedor   = st.text_input("Fornecedor")
            fase         = st.selectbox("Fase", ["4.2", "4.1", "5.0"])
        with col2:
            qtd_pedida   = st.number_input("Qtd Pedida *", min_value=1, value=1)
            valor_unit   = st.number_input("Valor Unitário (R$)", min_value=0.0, value=0.0, format="%.2f")
            num_pedido   = st.text_input("Nº do Pedido")
            data_pedido  = st.date_input("Data do Pedido", value=date.today())

        nf = st.text_input("Nota Fiscal (NF)")

        submitted = st.form_submit_button("💾 Salvar Compra", use_container_width=True, type="primary")

    if submitted:
        try:
            sb.table("compras").insert({
                "parceiro_id":    parceiros[parceiro_sel],
                "item_id":        itens_dict[item_sel],
                "fornecedor":     fornecedor or None,
                "qtd_pedida":     int(qtd_pedida),
                "qtd_recebida":   0,
                "valor_unitario": float(valor_unit) if valor_unit > 0 else None,
                "numero_pedido":  num_pedido or None,
                "nf":             nf or None,
                "fase":           fase,
                "data_pedido":    str(data_pedido),
            }).execute()
            st.success(f"✅ Compra registrada com sucesso!")
            st.cache_data.clear()
            st.rerun()
        except Exception as e:
            st.error(f"Erro ao salvar: {e}")

# ══════════════════════════════════════════════════════════════════════════════
# ABA 2 — CONFIRMAR RECEBIMENTO
# ══════════════════════════════════════════════════════════════════════════════
with tab2:
    st.subheader("Confirmar recebimento de mercadoria")

    df_compras = carregar_compras()

    # Mostra apenas compras onde qtd_recebida < qtd_pedida
    df_pendentes = df_compras[df_compras["Qtd Recebida"] < df_compras["Qtd Pedida"]].copy()

    if df_pendentes.empty:
        st.info("✅ Nenhum pedido pendente de recebimento!")
    else:
        st.caption(f"{len(df_pendentes)} pedido(s) aguardando recebimento")
        st.dataframe(df_pendentes[["ID","Parceiro","Item","Fornecedor","Qtd Pedida","Qtd Recebida","NF","Data Pedido"]],
                     use_container_width=True, hide_index=True)

        st.markdown("---")
        st.markdown("**Registrar recebimento:**")

        col1, col2, col3 = st.columns(3)
        with col1:
            id_sel = st.number_input("ID da Compra", min_value=1, step=1)
        with col2:
            qtd_rec = st.number_input("Qtd Recebida", min_value=1, step=1)
        with col3:
            data_rec = st.date_input("Data de Recebimento", value=date.today())

        nf_rec = st.text_input("Nota Fiscal (NF)", key="nf_rec")

        if st.button("✅ Confirmar Recebimento", type="primary", use_container_width=True):
            try:
                update_data = {
                    "qtd_recebida":      int(qtd_rec),
                    "data_recebimento":  str(data_rec),
                }
                if nf_rec:
                    update_data["nf"] = nf_rec
                sb.table("compras").update(update_data).eq("id", int(id_sel)).execute()
                st.success(f"✅ Recebimento da compra #{id_sel} confirmado!")
                st.cache_data.clear()
                st.rerun()
            except Exception as e:
                st.error(f"Erro: {e}")

# ══════════════════════════════════════════════════════════════════════════════
# ABA 3 — HISTÓRICO
# ══════════════════════════════════════════════════════════════════════════════
with tab3:
    st.subheader("Histórico de compras")

    df_compras2 = carregar_compras()

    col1, col2 = st.columns(2)
    with col1:
        parc_filtro = st.selectbox("Filtrar por Parceiro", ["Todos"] + sorted(df_compras2["Parceiro"].unique().tolist()), key="hist_parc")
    with col2:
        fase_filtro = st.selectbox("Filtrar por Fase", ["Todas"] + sorted(df_compras2["Fase"].unique().tolist()), key="hist_fase")

    df_hist = df_compras2.copy()
    if parc_filtro != "Todos":
        df_hist = df_hist[df_hist["Parceiro"] == parc_filtro]
    if fase_filtro != "Todas":
        df_hist = df_hist[df_hist["Fase"] == fase_filtro]

    st.dataframe(df_hist, use_container_width=True, hide_index=True, height=500)

    st.download_button(
        "⬇️ Exportar (.csv)",
        data=df_hist.to_csv(index=False).encode("utf-8"),
        file_name="historico_compras.csv",
        mime="text/csv",
    )
