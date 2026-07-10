"""Tema IUH Digital — aplicar em todas as páginas do app."""
import base64
import pathlib
import streamlit as st

IUH_TEAL   = "#0C6679"
IUH_ACCENT = "#2EDBA0"
IUH_DARK   = "#0a4a5a"

_CSS = f"""
<style>
/* ── Base ── */
html, body, [data-testid="stAppViewContainer"] {{
    background: #f0f4f8;
    font-family: 'Segoe UI', Arial, sans-serif;
}}
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
    background: #0a5568 !important;
}}

/* ── KPI Metric cards ── */
[data-testid="stMetric"] {{
    background: #ffffff;
    border-radius: 10px;
    padding: 1rem 1.1rem 0.9rem;
    border-left: 4px solid {IUH_ACCENT};
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

/* ── Tabs ── */
[data-testid="stTabs"] [data-baseweb="tab-list"] {{
    background: white;
    border-radius: 8px 8px 0 0;
    padding: 0 0.5rem;
    box-shadow: 0 1px 4px rgba(0,0,0,0.06);
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

/* ── Headings ── */
h2, h3 {{ color: {IUH_DARK} !important; font-weight: 700 !important; }}

/* ── Multiselect tag ── */
[data-baseweb="tag"] {{ background-color: {IUH_TEAL} !important; }}

/* ── Buttons ── */
.stDownloadButton > button,
.stButton [kind="primary"] {{
    background-color: {IUH_TEAL} !important;
    border: none !important;
    color: white !important;
    font-weight: 700 !important;
    border-radius: 7px !important;
}}

/* ── Divider ── */
hr {{ border-color: #e2e8f0 !important; margin: 1.2rem 0 !important; }}

/* ── Page header card ── */
.iuh-header {{
    background: white;
    border-radius: 12px;
    padding: 1.1rem 1.5rem;
    margin-bottom: 1.2rem;
    box-shadow: 0 1px 6px rgba(0,0,0,0.07);
    border-left: 5px solid {IUH_ACCENT};
}}
.iuh-header-title {{
    font-size: 1.4rem;
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
    border-bottom: 1px solid #1a4a57;
    padding: 1rem 1.2rem 0.8rem;
    margin-bottom: 0.5rem;
    text-align: center;
}}
.iuh-logo-sub {{
    font-size: 0.6rem;
    letter-spacing: 0.22em;
    color: #94a3b8 !important;
    font-weight: 700;
    text-transform: uppercase;
    margin-top: 4px;
    display: block;
}}
</style>
"""

_LOGO_PATH = pathlib.Path(__file__).parent.parent / "assets" / "logo_iuh.png"


def _logo_b64() -> str:
    if _LOGO_PATH.exists():
        return base64.b64encode(_LOGO_PATH.read_bytes()).decode()
    return ""


def aplicar_tema():
    """Injeta CSS IUH + logo na sidebar. Chamar no topo de cada página."""
    st.markdown(_CSS, unsafe_allow_html=True)


def sidebar_logo(subtitulo: str = ""):
    """Exibe logo IUH + subtítulo no topo da sidebar."""
    b64 = _logo_b64()
    if b64:
        img_tag = (
            f'<img src="data:image/png;base64,{b64}" '
            f'style="width:130px; display:block; margin:0 auto; '
            f'filter:brightness(0) invert(1);" />'
        )
    else:
        img_tag = '<div style="color:#2EDBA0;font-size:1.8rem;font-weight:900;">iuh!</div>'

    sub = f'<span class="iuh-logo-sub">{subtitulo}</span>' if subtitulo else ""
    st.sidebar.markdown(
        f'<div class="iuh-logo-box">{img_tag}{sub}</div>',
        unsafe_allow_html=True,
    )


def page_header(titulo: str, subtitulo: str = ""):
    """Card de header padronizado IUH no topo da página."""
    sub_html = f'<p class="iuh-header-sub">{subtitulo}</p>' if subtitulo else ""
    st.markdown(
        f'<div class="iuh-header">'
        f'<p class="iuh-header-title">{titulo}</p>{sub_html}'
        f'</div>',
        unsafe_allow_html=True,
    )
