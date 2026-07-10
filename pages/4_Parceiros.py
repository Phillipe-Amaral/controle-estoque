import streamlit as st
from supabase import create_client
import pandas as pd
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from utils.tema_iuh import aplicar_tema, sidebar_logo, page_header

st.set_page_config(page_title="Parceiros", page_icon="🤝", layout="wide")
aplicar_tema()
sidebar_logo("Parceiros")

SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]

@st.cache_resource
def get_client():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

sb = get_client()

@st.cache_data(ttl=30)
def carregar_parceiros():
    r = sb.table("parceiros").select("id, nome, razao_social, cnpj, uf, fase").order("nome").execute()
    colunas = ["ID","Nome Fantasia","Razão Social","CNPJ","UF","Fase"]
    rows = []
    for p in r.data:
        rows.append({
            "ID":           p["id"],
            "Nome Fantasia":p["nome"] or "",
            "Razão Social": p.get("razao_social") or "",
            "CNPJ":         p.get("cnpj") or "",
            "UF":           p.get("uf") or "",
            "Fase":         p.get("fase") or "",
        })
    return pd.DataFrame(rows, columns=colunas) if rows else pd.DataFrame(columns=colunas)

page_header("🤝 Cadastro de Parceiros", "Gerencie os parceiros com razão social, nome fantasia e CNPJ")

tab1, tab2 = st.tabs(["📋 Lista de Parceiros", "➕ Novo / Editar Parceiro"])

# ══════════════════════════════════════════════════════════════════════════════
# ABA 1 — LISTA
# ══════════════════════════════════════════════════════════════════════════════
with tab1:
    df = carregar_parceiros()

    busca = st.text_input("🔍 Buscar por nome fantasia, razão social ou CNPJ")
    if busca:
        mask = (
            df["Nome Fantasia"].str.contains(busca, case=False, na=False) |
            df["Razão Social"].str.contains(busca, case=False, na=False) |
            df["CNPJ"].str.contains(busca, case=False, na=False)
        )
        df = df[mask]

    st.dataframe(df, use_container_width=True, hide_index=True, height=500)
    st.caption(f"{len(df)} parceiro(s) encontrado(s)")

    st.download_button(
        "⬇️ Exportar (.csv)",
        data=df.to_csv(index=False).encode("utf-8"),
        file_name="parceiros.csv",
        mime="text/csv",
    )

# ══════════════════════════════════════════════════════════════════════════════
# ABA 2 — CADASTRO / EDIÇÃO
# ══════════════════════════════════════════════════════════════════════════════
with tab2:
    df_todos = carregar_parceiros()

    modo = st.radio("Modo", ["Novo parceiro", "Editar existente"], horizontal=True)

    if modo == "Editar existente":
        opcoes = {f"{r['Nome Fantasia']} (ID {r['ID']})": r for _, r in df_todos.iterrows()}
        sel = st.selectbox("Selecione o parceiro", list(opcoes.keys()))
        dados = opcoes[sel]
        id_edit = int(dados["ID"])
    else:
        dados = {}
        id_edit = None

    with st.form("form_parceiro", clear_on_submit=(modo == "Novo parceiro")):
        col1, col2 = st.columns(2)
        with col1:
            nome_f    = st.text_input("Nome Fantasia *", value=dados.get("Nome Fantasia",""))
            razao     = st.text_input("Razão Social",    value=dados.get("Razão Social",""))
            cnpj      = st.text_input("CNPJ",            value=dados.get("CNPJ",""), placeholder="00.000.000/0001-00")
        with col2:
            uf        = st.text_input("UF (estado principal)", value=dados.get("UF",""), max_chars=2)
            fase      = st.selectbox("Fase principal", ["","4.1","4.2","4.2 Adicional","5.0"],
                                     index=["","4.1","4.2","4.2 Adicional","5.0"].index(dados.get("Fase","")) if dados.get("Fase","") in ["","4.1","4.2","4.2 Adicional","5.0"] else 0)

        label = "💾 Salvar Alterações" if modo == "Editar existente" else "➕ Cadastrar Parceiro"
        submitted = st.form_submit_button(label, use_container_width=True, type="primary")

    if submitted:
        if not nome_f:
            st.error("Nome Fantasia é obrigatório.")
        else:
            payload = {
                "nome":         nome_f.strip().upper(),
                "razao_social": razao.strip() or None,
                "cnpj":         cnpj.strip() or None,
                "uf":           uf.strip().upper() or None,
                "fase":         fase or None,
            }
            try:
                if modo == "Editar existente" and id_edit:
                    sb.table("parceiros").update(payload).eq("id", id_edit).execute()
                    st.success(f"✅ Parceiro **{nome_f}** atualizado!")
                else:
                    sb.table("parceiros").insert(payload).execute()
                    st.success(f"✅ Parceiro **{nome_f}** cadastrado!")
                st.cache_data.clear()
                st.rerun()
            except Exception as e:
                st.error(f"Erro: {e}")
