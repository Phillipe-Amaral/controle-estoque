import streamlit as st
from supabase import create_client
import pandas as pd
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from utils.tema_iuh import aplicar_tema, sidebar_logo, page_header

st.set_page_config(page_title="Cadastros", page_icon="📋", layout="wide")
aplicar_tema()
sidebar_logo("Cadastros")

SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]

@st.cache_resource
def get_client():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

sb = get_client()

@st.cache_data(ttl=30)
def carregar_itens():
    r = sb.table("itens").select("id, nome, fabricante").order("nome").execute()
    return r.data

@st.cache_data(ttl=30)
def carregar_de_para():
    r = sb.table("de_para_itens_adicionais").select("*").order("id_lpu").execute()
    return pd.DataFrame(r.data) if r.data else pd.DataFrame()

@st.cache_data(ttl=30)
def carregar_similares():
    r = sb.table("itens_similares").select("*").order("id").execute()
    return pd.DataFrame(r.data) if r.data else pd.DataFrame()

page_header("📋 Cadastros Auxiliares", "")

tab1, tab2 = st.tabs(["🔄 DE/PARA — Itens Adicionais", "🔗 Itens Similares"])

# ══════════════════════════════════════════════════════════════════════════════
# ABA 1 — DE/PARA ITENS ADICIONAIS
# ══════════════════════════════════════════════════════════════════════════════
with tab1:
    st.subheader("DE/PARA: nome LPU (snake_case) → Item no banco")
    st.caption(
        "Tabela que relaciona o nome do item adicional conforme descrito na LPU "
        "(ex: `controladora_firewall_wifi`) ao item físico cadastrado no banco, por fabricante."
    )

    df_dp = carregar_de_para()

    if not df_dp.empty:
        itens_db   = carregar_itens()
        item_map   = {i["id"]: f"{i['nome']} ({i['fabricante'] or '—'})" for i in itens_db}
        item_inv   = {v: k for k, v in item_map.items()}

        col_rename = {
            "id":           "ID",
            "id_lpu":       "ID LPU",
            "item_lpu":     "Item na LPU",
            "item_sistema": "Nome Sistema",
            "fabricante":   "Fabricante",
            "descricao":    "Descrição",
            "codigo_item":  "Cód. Item",
            "funcao":       "Função",
            "part_number":  "Part Number",
            "item_id":      "Item ID banco",
        }
        df_show = df_dp.rename(columns=col_rename)
        if "Item ID banco" in df_show.columns:
            df_show["Item no banco"] = df_show["Item ID banco"].map(item_map)

        st.dataframe(df_show, use_container_width=True, hide_index=True, height=420)

        st.download_button(
            "⬇️ Exportar (.csv)",
            data=df_show.to_csv(index=False).encode("utf-8"),
            file_name="de_para_itens_adicionais.csv",
            mime="text/csv",
        )

    st.markdown("---")
    with st.expander("➕ Adicionar novo mapeamento"):
        itens_db2  = carregar_itens()
        itens_dict = {f"{i['nome']} ({i['fabricante'] or '—'})": i["id"] for i in itens_db2}

        with st.form("form_de_para", clear_on_submit=True):
            c1, c2 = st.columns(2)
            with c1:
                id_lpu      = st.number_input("ID LPU (20–35)", min_value=1, step=1)
                item_lpu    = st.text_input("Item na LPU (ex: Nobreak)")
                item_sis    = st.text_input("Nome sistema snake_case (ex: nobreak)")
                fabricante  = st.text_input("Fabricante (ex: INTELBRAS)")
            with c2:
                descricao   = st.text_input("Descrição do produto")
                codigo_item = st.text_input("Código do item")
                funcao      = st.text_input("Função (ex: SWITCH, ROTEADOR)")
                part_number = st.text_input("Part Number (nome no banco)")
                item_sel    = st.selectbox("Item no banco *", [""] + list(itens_dict.keys()))

            if st.form_submit_button("💾 Salvar", type="primary", use_container_width=True):
                if not item_sis or not fabricante:
                    st.error("Nome sistema e fabricante são obrigatórios.")
                else:
                    try:
                        sb.table("de_para_itens_adicionais").insert({
                            "id_lpu":      int(id_lpu),
                            "item_lpu":    item_lpu or None,
                            "item_sistema":item_sis,
                            "fabricante":  fabricante,
                            "descricao":   descricao or None,
                            "codigo_item": codigo_item or None,
                            "funcao":      funcao or None,
                            "part_number": part_number or None,
                            "item_id":     itens_dict[item_sel] if item_sel else None,
                        }).execute()
                        st.success("✅ Mapeamento salvo!")
                        st.cache_data.clear()
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro: {e}")

    with st.expander("🗑️ Remover mapeamento"):
        del_id = st.number_input("ID do registro a remover", min_value=1, step=1, key="del_dp")
        if st.button("Remover", type="secondary", key="btn_del_dp"):
            try:
                sb.table("de_para_itens_adicionais").delete().eq("id", int(del_id)).execute()
                st.success(f"Registro #{del_id} removido.")
                st.cache_data.clear()
                st.rerun()
            except Exception as e:
                st.error(f"Erro: {e}")

# ══════════════════════════════════════════════════════════════════════════════
# ABA 2 — ITENS SIMILARES
# ══════════════════════════════════════════════════════════════════════════════
with tab2:
    st.subheader("Itens Similares")
    st.caption(
        "Pares de itens que podem ser usados de forma intercambiável na instalação. "
        "O sistema aceita a baixa de qualquer similar quando o item principal não está disponível."
    )

    df_sim = carregar_similares()
    itens_db3  = carregar_itens()
    itens_dict3 = {f"{i['nome']} ({i['fabricante'] or '—'})": i["id"] for i in itens_db3}
    item_map3   = {i["id"]: f"{i['nome']} ({i['fabricante'] or '—'})" for i in itens_db3}

    if not df_sim.empty:
        df_show2 = df_sim.copy()
        if "item_id_a" in df_show2.columns:
            df_show2["Item A"] = df_show2["item_id_a"].map(item_map3)
        if "item_id_b" in df_show2.columns:
            df_show2["Item B (similar)"] = df_show2["item_id_b"].map(item_map3)
        cols_show = ["id", "Item A", "Item B (similar)"]
        if "observacao" in df_show2.columns:
            cols_show.append("observacao")
        st.dataframe(
            df_show2[[c for c in cols_show if c in df_show2.columns]],
            use_container_width=True, hide_index=True, height=360
        )
        st.download_button(
            "⬇️ Exportar (.csv)",
            data=df_show2.to_csv(index=False).encode("utf-8"),
            file_name="itens_similares.csv",
            mime="text/csv",
        )
    else:
        st.info("Nenhum par de similares cadastrado.")

    st.markdown("---")
    with st.expander("➕ Adicionar par de similares"):
        with st.form("form_similar", clear_on_submit=True):
            c1, c2 = st.columns(2)
            with c1:
                item_a = st.selectbox("Item A (principal)", list(itens_dict3.keys()), key="sim_a")
            with c2:
                item_b = st.selectbox("Item B (similar)", list(itens_dict3.keys()), key="sim_b")
            obs = st.text_input("Observação (opcional)")

            if st.form_submit_button("💾 Salvar par", type="primary", use_container_width=True):
                id_a = itens_dict3[item_a]
                id_b = itens_dict3[item_b]
                if id_a == id_b:
                    st.error("Os itens devem ser diferentes.")
                else:
                    try:
                        sb.table("itens_similares").insert({
                            "item_id_a":   id_a,
                            "item_id_b":   id_b,
                            "observacao":  obs or None,
                        }).execute()
                        st.success("✅ Par salvo!")
                        st.cache_data.clear()
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro: {e}")

    with st.expander("🗑️ Remover par"):
        del_sim = st.number_input("ID do par a remover", min_value=1, step=1, key="del_sim")
        if st.button("Remover", type="secondary", key="btn_del_sim"):
            try:
                sb.table("itens_similares").delete().eq("id", int(del_sim)).execute()
                st.success(f"Par #{del_sim} removido.")
                st.cache_data.clear()
                st.rerun()
            except Exception as e:
                st.error(f"Erro: {e}")
