import streamlit as st
from supabase import create_client
import pandas as pd
from datetime import date

st.set_page_config(page_title="Topologia", page_icon="🏫", layout="wide")

SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]

@st.cache_resource
def get_client():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

sb = get_client()

# ── Helpers ───────────────────────────────────────────────────────────────────
@st.cache_data(ttl=60)
def carregar_parceiros():
    r = sb.table("parceiros").select("id, nome").order("nome").execute()
    return {p["nome"]: p["id"] for p in r.data}

@st.cache_data(ttl=60)
def carregar_item_map():
    r = sb.table("itens").select("id, nome").execute()
    return {i["id"]: i["nome"] for i in r.data}

@st.cache_data(ttl=300)
def carregar_topologia_opcoes():
    r = sb.table("topologias").select("fase, fabricante, uf").execute()
    df = pd.DataFrame(r.data)
    if df.empty:
        return [], [], []
    fases = sorted(df["fase"].dropna().unique().tolist())
    fabs  = sorted(df["fabricante"].dropna().unique().tolist())
    ufs   = sorted(df["uf"].dropna().unique().tolist())
    return fases, fabs, ufs

@st.cache_data(ttl=60)
def buscar_topologia(fase, fabricante, uf, kit_numero):
    r = (sb.table("topologias")
         .select("funcao_item, item_id, qtd, descricao, observacao")
         .eq("fase", fase).eq("fabricante", fabricante)
         .eq("uf", uf).eq("kit_numero", kit_numero)
         .gt("qtd", 0)
         .execute())
    return r.data

@st.cache_data(ttl=60)
def carregar_instalacoes():
    r = (sb.table("execucoes")
         .select("id, parceiro_id, nome_escola, codigo_inep, municipio, uf, kit, fase, data_implantacao")
         .order("id", desc=True)
         .execute())
    rp = sb.table("parceiros").select("id, nome").execute()
    parc_map = {p["id"]: p["nome"] for p in rp.data}
    rows = []
    for e in r.data:
        rows.append({
            "ID":        e["id"],
            "Parceiro":  parc_map.get(e["parceiro_id"], ""),
            "Escola":    e["nome_escola"] or "",
            "INEP":      e["codigo_inep"] or "",
            "Município": e["municipio"] or "",
            "UF":        e["uf"] or "",
            "APs":       e["kit"] or 0,
            "Fase":      e["fase"] or "",
            "Data":      e["data_implantacao"] or "",
        })
    cols = ["ID","Parceiro","Escola","INEP","Município","UF","APs","Fase","Data"]
    return pd.DataFrame(rows, columns=cols) if rows else pd.DataFrame(columns=cols)

# ── Título ────────────────────────────────────────────────────────────────────
st.title("🏫 Gestão de Topologia")
st.caption("Cadastre instalações por escola e gere baixas automáticas de estoque via topologia")

tab1, tab2, tab3 = st.tabs(["📐 Consultar Topologia", "➕ Registrar Instalação", "📋 Histórico de Instalações"])

# ══════════════════════════════════════════════════════════════════════════════
# ABA 1 — CONSULTAR TOPOLOGIA
# ══════════════════════════════════════════════════════════════════════════════
with tab1:
    st.subheader("Consultar topologia por escola")
    st.info("Selecione a combinação de Fase + Fabricante + UF + nº de APs para ver os itens da instalação.")

    fases, fabs, ufs = carregar_topologia_opcoes()

    if not fases:
        st.warning("Topologia ainda não importada. Execute o SQL de importação no Supabase.")
    else:
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            fase_sel = st.selectbox("Fase", fases, key="t_fase")
        with col2:
            fab_sel  = st.selectbox("Fabricante", fabs, key="t_fab")
        with col3:
            uf_sel   = st.selectbox("UF", ufs, key="t_uf")
        with col4:
            num_aps  = st.number_input("Nº de APs (kit)", min_value=1, max_value=48, value=1, key="t_aps")

        itens_topo = buscar_topologia(fase_sel, fab_sel, uf_sel, num_aps)

        if itens_topo:
            item_map = carregar_item_map()
            df_topo = pd.DataFrame(itens_topo)
            df_topo["Item"] = df_topo["item_id"].apply(lambda x: item_map.get(x, "—") if x else "—")
            df_topo = df_topo.rename(columns={
                "funcao_item": "Função", "qtd": "Qtd",
                "descricao": "Descrição", "observacao": "Obs"
            })[["Função", "Item", "Qtd", "Descrição", "Obs"]]

            st.success(f"**{len(df_topo)} itens** para instalação com **{num_aps} AP(s)** — {fab_sel} / {fase_sel} / {uf_sel}")
            st.dataframe(df_topo, use_container_width=True, hide_index=True)

            total_cabo = df_topo[df_topo["Função"] == "CABO"]["Qtd"].sum()
            if total_cabo:
                st.caption(f"Cabo total: {total_cabo} metros")
        else:
            st.warning(f"Nenhuma topologia encontrada para {fab_sel} / {fase_sel} / {uf_sel} / {num_aps} APs.")

# ══════════════════════════════════════════════════════════════════════════════
# ABA 2 — REGISTRAR INSTALAÇÃO (DE/PARA → BAIXA)
# ══════════════════════════════════════════════════════════════════════════════
with tab2:
    st.subheader("Registrar instalação e gerar baixa de estoque")
    st.info("Informe os dados da escola e o sistema calculará automaticamente os itens baixados do estoque do parceiro.")

    parceiros   = carregar_parceiros()
    fases2, fabs2, ufs2 = carregar_topologia_opcoes()

    with st.form("form_instalacao"):
        col1, col2 = st.columns(2)
        with col1:
            parceiro_sel = st.selectbox("Parceiro *", list(parceiros.keys()))
            fase_i       = st.selectbox("Fase *", fases2 if fases2 else ["4.1","4.2","5.0"])
            fabricante_i = st.selectbox("Fabricante *", fabs2 if fabs2 else ["INTELBRAS","TP-LINK","DATACOM"])
            uf_i         = st.selectbox("UF *", ufs2 if ufs2 else ["MG","SP","RJ","ES","BA","PA","AM","CE"])
        with col2:
            num_aps_i    = st.number_input("Nº de APs instalados *", min_value=1, max_value=48, value=1)
            nome_escola  = st.text_input("Nome da Escola *")
            cod_inep     = st.text_input("Código INEP")
            municipio    = st.text_input("Município")
            data_inst    = st.date_input("Data da Instalação", value=date.today())

        submitted = st.form_submit_button("🔍 Pré-visualizar Baixa", use_container_width=True)

    if submitted:
        if not nome_escola:
            st.error("Informe o nome da escola.")
        else:
            itens_calc = buscar_topologia(fase_i, fabricante_i, uf_i, num_aps_i)
            if not itens_calc:
                st.error(f"Topologia não encontrada para {fabricante_i} / {fase_i} / {uf_i} / {num_aps_i} APs.")
            else:
                item_map = carregar_item_map()
                st.markdown("---")
                st.markdown(f"### Itens que serão baixados do estoque de **{parceiro_sel}**")

                preview = []
                for it in itens_calc:
                    preview.append({
                        "Função":  it["funcao_item"],
                        "Item":    item_map.get(it["item_id"], "—") if it["item_id"] else "—",
                        "Qtd":     it["qtd"],
                        "item_id": it["item_id"],
                    })
                df_prev = pd.DataFrame(preview)
                st.dataframe(df_prev[["Função","Item","Qtd"]], use_container_width=True, hide_index=True)

                st.session_state["prev_instalacao"] = {
                    "parceiro_id":  parceiros[parceiro_sel],
                    "parceiro_nome": parceiro_sel,
                    "fase":          fase_i,
                    "fabricante":    fabricante_i,
                    "uf":            uf_i,
                    "kit":           num_aps_i,
                    "nome_escola":   nome_escola,
                    "cod_inep":      cod_inep,
                    "municipio":     municipio,
                    "data_inst":     str(data_inst),
                    "itens":         [i for i in itens_calc if i["item_id"]],
                }
                st.session_state["prev_df"] = df_prev

    # Botão de confirmação fora do form
    if "prev_instalacao" in st.session_state:
        prev = st.session_state["prev_instalacao"]
        st.warning(f"⚠️ Confirmar baixa de **{len(prev['itens'])} itens** para **{prev['nome_escola']}** ({prev['parceiro_nome']})?")

        col_a, col_b = st.columns(2)
        with col_a:
            if st.button("✅ Confirmar e Baixar Estoque", type="primary", use_container_width=True):
                try:
                    # 1. Cria execucao
                    exec_resp = sb.table("execucoes").insert({
                        "parceiro_id":      prev["parceiro_id"],
                        "nome_escola":      prev["nome_escola"],
                        "codigo_inep":      prev["cod_inep"] or None,
                        "municipio":        prev["municipio"] or None,
                        "uf":               prev["uf"],
                        "kit":              prev["kit"],
                        "fase":             prev["fase"],
                        "data_implantacao": prev["data_inst"],
                    }).execute()

                    exec_id = exec_resp.data[0]["id"]

                    # 2. Cria execucao_itens
                    itens_insert = [
                        {"execucao_id": exec_id, "item_id": it["item_id"], "qtd": it["qtd"]}
                        for it in prev["itens"] if it["qtd"] > 0
                    ]
                    sb.table("execucao_itens").insert(itens_insert).execute()

                    st.success(f"✅ Instalação registrada! Execução #{exec_id} — {len(itens_insert)} itens baixados do estoque de {prev['parceiro_nome']}.")
                    del st.session_state["prev_instalacao"]
                    if "prev_df" in st.session_state:
                        del st.session_state["prev_df"]
                    st.cache_data.clear()
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro ao registrar: {e}")
        with col_b:
            if st.button("❌ Cancelar", use_container_width=True):
                del st.session_state["prev_instalacao"]
                if "prev_df" in st.session_state:
                    del st.session_state["prev_df"]
                st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
# ABA 3 — HISTÓRICO
# ══════════════════════════════════════════════════════════════════════════════
with tab3:
    st.subheader("Histórico de instalações registradas")

    df_inst = carregar_instalacoes()

    col1, col2, col3 = st.columns(3)
    with col1:
        parc_f = st.selectbox("Parceiro", ["Todos"] + sorted(df_inst["Parceiro"].unique().tolist()) if not df_inst.empty else ["Todos"], key="h_parc")
    with col2:
        fase_f = st.selectbox("Fase", ["Todas"] + sorted(df_inst["Fase"].unique().tolist()) if not df_inst.empty else ["Todas"], key="h_fase")
    with col3:
        uf_f   = st.selectbox("UF", ["Todas"] + sorted(df_inst["UF"].unique().tolist()) if not df_inst.empty else ["Todas"], key="h_uf")

    df_view = df_inst.copy()
    if parc_f != "Todos":
        df_view = df_view[df_view["Parceiro"] == parc_f]
    if fase_f != "Todas":
        df_view = df_view[df_view["Fase"] == fase_f]
    if uf_f != "Todas":
        df_view = df_view[df_view["UF"] == uf_f]

    col_m1, col_m2, col_m3 = st.columns(3)
    col_m1.metric("Total de Escolas", len(df_view))
    col_m2.metric("Total de APs", int(df_view["APs"].sum()) if not df_view.empty else 0)
    col_m3.metric("Parceiros distintos", df_view["Parceiro"].nunique() if not df_view.empty else 0)

    st.dataframe(df_view, use_container_width=True, hide_index=True, height=500)

    st.download_button(
        "⬇️ Exportar (.csv)",
        data=df_view.to_csv(index=False).encode("utf-8"),
        file_name="historico_instalacoes.csv",
        mime="text/csv",
    )
