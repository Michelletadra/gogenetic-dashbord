"""Código compartilhado entre todas as páginas do dashboard."""
import json
import os
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import plotly.graph_objects as go
import streamlit as st
import streamlit_authenticator as stauth
from dotenv import load_dotenv

from egestor_api import EgestorClient

# ── Credenciais de acesso ─────────────────────────────────────────────────────
_HASH = "$2b$12$lps5s0dBc/0dPNDuOHsKOesTq1zB/plaildClr3yVKJtTyiZAy20O"
CREDENTIALS = {
    "usernames": {
        "michelle": {"name": "Michelle Tadra",        "email": "michelle@gogenetic.com.br",      "password": _HASH},
        "neto":     {"name": "Silvino Souza Neto",    "email": "souza.neto@gogenetic.com.br",    "password": _HASH},
        "joseneis": {"name": "Joseneis Ribeiro Lima", "email": "jo@gogenetic.com.br",            "password": _HASH},
        "vania":    {"name": "Vânia Pankievicz",      "email": "vania@gogenetic.com.br",         "password": _HASH},
        "eduardo":  {"name": "Eduardo Balsanelli",    "email": "balsanelli@gogenetic.com.br",    "password": _HASH},
        "amanda":   {"name": "Amanda Mara S. Souza",  "email": "amanda@gogenetic.com.br",        "password": _HASH},
    }
}

def get_authenticator() -> stauth.Authenticate:
    if "_authenticator" not in st.session_state:
        st.session_state["_authenticator"] = stauth.Authenticate(
            CREDENTIALS,
            cookie_name="gogenetic_auth",
            cookie_key="gogenetic_secret_2026",
            cookie_expiry_days=30,
            auto_hash=False,
        )
    return st.session_state["_authenticator"]

def require_auth():
    """Para a execução da página se o usuário não estiver autenticado."""
    if not st.session_state.get("authentication_status"):
        st.error("🔒 Faça login na página inicial para acessar o dashboard.")
        st.stop()

load_dotenv()

def _secret(key: str, default: str = "") -> str:
    """Lê do .env local ou dos secrets do Streamlit Cloud."""
    val = os.getenv(key)
    if val:
        return val
    try:
        return st.secrets[key]
    except Exception:
        return default

ASSETS   = Path(__file__).parent / "assets"
METAS_FILE = Path(__file__).parent / "metas.json"

# ── Identidade visual ─────────────────────────────────────────────────────────

BRAND = {
    "GoGenetic Pesquisa": {
        "logo":    str(ASSETS / "logo_gg.png"),
        "primary": "#7E16B8",
        "dark":    "#370950",
        "light":   "#CD76FF",
        "accent":  "#24B78C",
        "source":  "egestor",
    },
    "GoGenetic Soluções": {
        "logo":    str(ASSETS / "logo_gga.png"),
        "primary": "#3ADFB0",
        "dark":    "#051F18",
        "light":   "#7CEDCC",
        "accent":  "#24B78C",
        "source":  "egestor",
    },
    "GoSolos": {
        "logo":    str(ASSETS / "logo_gs.png"),
        "primary": "#FF672F",
        "dark":    "#4A1E0E",
        "light":   "#FF9C6B",
        "accent":  "#FFC0A1",
        "source":  "egestor",
    },
    "GoGenetic You": {
        "logo":    str(ASSETS / "logo_ggy.png"),
        "primary": "#13CFE8",
        "dark":    "#190E33",
        "light":   "#7AEAF5",
        "accent":  "#0E62AA",
        "source":  "bling",
    },
}

EMPRESAS_EGESTOR = [
    {"nome": _secret("GOGENETIC_PESQUISA_NOME", "GoGenetic Pesquisa"), "token": _secret("GOGENETIC_PESQUISA_TOKEN")},
    {"nome": _secret("GOGENETIC_SOLUCOES_NOME", "GoGenetic Soluções"), "token": _secret("GOGENETIC_SOLUCOES_TOKEN")},
    {"nome": _secret("GOSOLOS_NOME", "GoSolos"),                        "token": _secret("GOSOLOS_TOKEN")},
]
NOME_YOU     = _secret("GOGENETIC_YOU_NOME", "GoGenetic You")
EMPRESAS     = EMPRESAS_EGESTOR  # eGestor only (You é carregado separado via Bling)
NOMES        = [e["nome"] for e in EMPRESAS_EGESTOR]
TODOS_NOMES  = NOMES + [NOME_YOU]
CHART_COLORS = {n: BRAND[n]["primary"] for n in TODOS_NOMES if n in BRAND}

MESES_PT = {
    1: "Janeiro", 2: "Fevereiro", 3: "Março",    4: "Abril",
    5: "Maio",    6: "Junho",     7: "Julho",     8: "Agosto",
    9: "Setembro",10: "Outubro",  11: "Novembro", 12: "Dezembro",
}

# ── CSS global ────────────────────────────────────────────────────────────────

GLOBAL_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

/* ── Background principal ──────────────────────────────────────────── */
[data-testid="stAppViewContainer"],
[data-testid="stMain"],
.main { background-color: #F5F4FA !important; }
[data-testid="block-container"] { background-color: transparent !important; }

/* ── KPI Cards ─────────────────────────────────────────────────────── */
.kpi-card {
    background: #FFFFFF;
    border-radius: 16px;
    padding: 20px 22px 16px 22px;
    border: 1px solid #EAE6F4;
    box-shadow: 0 1px 6px rgba(126,22,184,0.06);
    transition: box-shadow .2s, border-color .2s;
    min-height: 100px;
}
.kpi-card:hover {
    box-shadow: 0 4px 18px rgba(126,22,184,0.13);
    border-color: rgba(126,22,184,0.28);
}
.kpi-icon-wrap {
    display: inline-flex; align-items: center; justify-content: center;
    width: 38px; height: 38px; border-radius: 10px;
    background: #EDE9F8; margin-bottom: 12px; font-size: 1.1rem;
}
.kpi-label {
    font-size: .72rem; text-transform: uppercase; letter-spacing: 1.2px;
    color: #8B6BAE; margin-bottom: 4px; font-weight: 600;
}
.kpi-value   { font-size: 1.45rem; font-weight: 700; color: #1A1033; line-height: 1.2; }
.kpi-sub     { font-size: .68rem; color: #A899C4; margin-top: 5px; }
.kpi-positive{ color: #10B981 !important; }
.kpi-negative{ color: #EF4444 !important; }
.kpi-warn    { color: #F59E0B !important; }

/* ── Section titles ────────────────────────────────────────────────── */
.section-title {
    font-size: .7rem; text-transform: uppercase; letter-spacing: 2px;
    color: #8B6BAE; font-weight: 700; margin: 28px 0 16px 0;
    padding-bottom: 8px; border-bottom: 1px solid #EAE6F4;
}

/* ── Page header ───────────────────────────────────────────────────── */
.page-title { font-size: 1.55rem; font-weight: 700; color: #1A1033; margin: 0 0 4px 0; }
.page-sub   { font-size: .82rem; color: #8B6BAE; margin: 0 0 24px 0; font-weight: 400; }

/* ── Sidebar ───────────────────────────────────────────────────────── */
[data-testid="stSidebar"] {
    background: #1E1535 !important;
    border-right: 1px solid rgba(126,22,184,0.15) !important;
}
[data-testid="stSidebarNav"] a { color: #D4C8EE !important; font-size: .88rem !important; }
[data-testid="stSidebarNav"] a:hover { color: #FFFFFF !important; }
[data-testid="stSidebar"] label { color: #A899C4 !important; font-size: .78rem !important; font-weight: 500 !important; }
[data-testid="stSidebar"] [data-baseweb="select"] > div {
    background: #2A1D4A !important;
    border-color: rgba(126,22,184,0.3) !important;
    border-radius: 10px !important;
    color: #EDE9F8 !important;
}
[data-testid="stSidebar"] p,
[data-testid="stSidebar"] span { color: #D4C8EE !important; }
[data-testid="stSidebar"] hr { border-color: rgba(126,22,184,0.2) !important; }
[data-testid="stSidebar"] button {
    background: #2A1D4A !important;
    border: 1px solid rgba(126,22,184,0.35) !important;
    color: #D4C8EE !important;
    border-radius: 10px !important;
    font-weight: 500 !important;
}
[data-testid="stSidebar"] button:hover {
    background: #7E16B8 !important;
    color: #FFFFFF !important;
    border-color: #7E16B8 !important;
}
[data-testid="stSidebar"] .stNumberInput input {
    background: #2A1D4A !important;
    color: #EDE9F8 !important;
    border-color: rgba(126,22,184,0.3) !important;
}

/* ── Tabs ──────────────────────────────────────────────────────────── */
button[data-baseweb="tab"] {
    font-size: .82rem !important;
    font-weight: 500 !important;
    color: #8B6BAE !important;
    border-radius: 8px 8px 0 0 !important;
}
button[data-baseweb="tab"][aria-selected="true"] {
    color: #7E16B8 !important;
    font-weight: 600 !important;
}

/* ── Dataframes / tables ───────────────────────────────────────────── */
[data-testid="stDataFrameResizable"] {
    border: 1px solid #EAE6F4 !important;
    border-radius: 12px !important;
    overflow: hidden;
}

/* ── Inputs & selectboxes (main area) ─────────────────────────────── */
[data-baseweb="select"] > div {
    border-radius: 10px !important;
    border-color: #EAE6F4 !important;
}

/* ── Metrics / info boxes ─────────────────────────────────────────── */
[data-testid="stMetric"] {
    background: #FFFFFF;
    border: 1px solid #EAE6F4;
    border-radius: 14px;
    padding: 16px 18px;
}

/* ── Download buttons ─────────────────────────────────────────────── */
[data-testid="stDownloadButton"] button {
    background: #7E16B8 !important;
    color: #FFFFFF !important;
    border: none !important;
    border-radius: 10px !important;
    font-weight: 500 !important;
}
[data-testid="stDownloadButton"] button:hover {
    background: #5E0F8A !important;
}
</style>
"""

# ── Helpers ────────────────────────────────────────────────────────────────────

def brl(value) -> str:
    try:
        return f"R$ {float(value):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return "R$ 0,00"


def status_badge(status: str) -> str:
    cores = {
        "VÁLIDO":    ("#10B981", "#D1FAE5"),
        "EXPIRADO":  ("#EF4444", "#FEE2E2"),
        "UTILIZADO": ("#6B7280", "#F3F4F6"),
        "CANCELADO": ("#F59E0B", "#FEF3C7"),
    }
    cor, bg = cores.get(status, ("#6B7280", "#F3F4F6"))
    return f'<span style="background:{bg};color:{cor};padding:2px 10px;border-radius:12px;font-size:.8rem;font-weight:600">{status}</span>'


def soma(items: list, campo: str) -> float:
    total = 0.0
    for it in items:
        try:
            total += float(it.get(campo) or 0)
        except (ValueError, TypeError):
            pass
    return total


def plotly_layout(fig, title: str = ""):
    fig.update_layout(
        title=dict(text=title, font=dict(size=13, color="#8B6BAE", family="Inter, sans-serif"), x=0),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, sans-serif", color="#1A1033", size=11),
        margin=dict(t=40, b=10, l=10, r=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0,
                    font=dict(size=10), bgcolor="rgba(0,0,0,0)"),
        xaxis=dict(gridcolor="rgba(126,22,184,0.06)", linecolor="rgba(126,22,184,0.12)", tickfont=dict(size=10, color="#8B6BAE")),
        yaxis=dict(gridcolor="rgba(126,22,184,0.06)", linecolor="rgba(126,22,184,0.12)", tickfont=dict(size=10, color="#8B6BAE")),
    )
    return fig


def kpi_card(col, icon: str, label: str, value: str, sub: str = "", border: str = "#EAE6F4", value_class: str = ""):
    col.markdown(f"""
    <div class="kpi-card" style="border-color:{border}">
      <div class="kpi-icon-wrap">{icon}</div>
      <div class="kpi-label">{label}</div>
      <div class="kpi-value {value_class}">{value}</div>
      {"<div class='kpi-sub'>" + sub + "</div>" if sub else ""}
    </div>""", unsafe_allow_html=True)


def sidebar_header(logo_path: Optional[str] = None):
    require_auth()
    with st.sidebar:
        if logo_path:
            st.image(logo_path, use_column_width=True)
        else:
            st.image(str(ASSETS / "logo_gg.png"), use_column_width=True)
        st.markdown(
            "<hr style='border:none;border-top:1px solid rgba(126,22,184,0.2);margin:12px 0 16px 0'>",
            unsafe_allow_html=True,
        )
        nome = st.session_state.get("name", "")
        st.caption(f"👤 {nome}")
        get_authenticator().logout("Sair", location="sidebar")


def sidebar_empresa_periodo(show_periodo: bool = True):
    """Retorna (empresas_ativas, dt_ini_str, dt_fim_str)."""
    with st.sidebar:
        empresa_opcoes = ["Todas"] + NOMES
        empresa_sel = st.selectbox("🏢 Empresa", empresa_opcoes)

        if empresa_sel != "Todas" and empresa_sel in BRAND:
            st.image(BRAND[empresa_sel]["logo"], use_column_width=True)

        empresas_ativas = NOMES if empresa_sel == "Todas" else [empresa_sel]
        dt_ini_str, dt_fim_str = "", ""

        if show_periodo:
            st.markdown("---")
            period_map = {
                "Este mês":        (date.today().replace(day=1), date.today()),
                "Últimos 30 dias": (date.today() - timedelta(days=30),  date.today()),
                "Últimos 60 dias": (date.today() - timedelta(days=60),  date.today()),
                "Últimos 90 dias": (date.today() - timedelta(days=90),  date.today()),
                "Este ano":        (date(date.today().year, 1, 1),       date.today()),
                "Personalizado":   None,
            }
            periodo_sel = st.selectbox("📅 Período", list(period_map.keys()))
            if periodo_sel == "Personalizado":
                c1, c2 = st.columns(2)
                dt_ini = c1.date_input("De",  date.today().replace(day=1))
                dt_fim = c2.date_input("Até", date.today())
            else:
                dt_ini, dt_fim = period_map[periodo_sel]
            dt_ini_str = dt_ini.strftime("%Y-%m-%d")
            dt_fim_str = dt_fim.strftime("%Y-%m-%d")

        st.markdown("---")
        if st.button("🔄 Atualizar dados", use_container_width=True):
            st.cache_data.clear()
            st.rerun()
        st.caption("⏱ Cache: 5 min")

    return empresas_ativas, dt_ini_str, dt_fim_str


# ── Metas ──────────────────────────────────────────────────────────────────────

def load_metas(ano: int) -> dict:
    if METAS_FILE.exists():
        data = json.loads(METAS_FILE.read_text())
        return {int(k): float(v) for k, v in data.get(str(ano), {}).items()}
    return {}


def save_metas(ano: int, metas: dict):
    data = {}
    if METAS_FILE.exists():
        data = json.loads(METAS_FILE.read_text())
    data[str(ano)] = {str(k): v for k, v in metas.items()}
    METAS_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False))


# ── API clients ────────────────────────────────────────────────────────────────

@st.cache_resource
def get_clients() -> dict:
    # Lê tokens em tempo de execução (não na importação) para garantir acesso ao st.secrets
    empresas = [
        {"nome": _secret("GOGENETIC_PESQUISA_NOME", "GoGenetic Pesquisa"), "token": _secret("GOGENETIC_PESQUISA_TOKEN")},
        {"nome": _secret("GOGENETIC_SOLUCOES_NOME", "GoGenetic Soluções"), "token": _secret("GOGENETIC_SOLUCOES_TOKEN")},
        {"nome": _secret("GOSOLOS_NOME", "GoSolos"),                        "token": _secret("GOSOLOS_TOKEN")},
    ]
    return {e["nome"]: EgestorClient(e["token"], e["nome"]) for e in empresas}


@st.cache_data(ttl=300, show_spinner=False)
def load_company_data(nome: str, dt_ini: str, dt_fim: str) -> dict:
    client = get_clients()[nome]
    try:
        return {
            "vendas":         client.get_vendas(dt_ini, dt_fim),
            "faturamento":    client.get_faturamento(dt_ini, dt_fim),
            "contas_receber": client.get_contas_receber(dt_ini, dt_fim),
            "contas_pagar":   client.get_contas_pagar(dt_ini, dt_fim),
        }
    except Exception as exc:
        st.error(f"Erro ao carregar {nome}: {exc}")
        return {"vendas": [], "faturamento": [], "contas_receber": [], "contas_pagar": []}


@st.cache_data(ttl=3600, show_spinner=False)
def load_vencidas(nome: str) -> dict:
    client = get_clients()[nome]
    try:
        return {"receber": client.get_vencidas_receber(), "pagar": client.get_vencidas_pagar()}
    except Exception:
        return {"receber": [], "pagar": []}


@st.cache_data(ttl=3600, show_spinner=False)
def load_vendas_ano(nome: str, ano: int) -> list:
    client = get_clients()[nome]
    try:
        return client.get_vendas(f"{ano}-01-01", f"{ano}-12-31")
    except Exception:
        return []


# ── Bling (GoGenetic You) ──────────────────────────────────────────────────────

def get_bling_client():
    """Retorna BlingClient se autenticado, None caso contrário."""
    try:
        import bling_auth
        import bling_api
        token = bling_auth.get_valid_token()
        if token:
            return bling_api.BlingClient(token, NOME_YOU)
    except Exception:
        pass
    return None


@st.cache_data(ttl=300, show_spinner=False)
def load_bling_data(dt_ini: str, dt_fim: str) -> dict:
    client = get_bling_client()
    if not client:
        return {"vendas": [], "faturamento": [], "contas_receber": [], "contas_pagar": []}
    try:
        from bling_api import BlingClient
        vendas_raw = client.get_vendas(dt_ini, dt_fim)
        fat_raw    = client.get_faturamento(dt_ini, dt_fim)
        rec_raw    = client.get_contas_receber(dt_ini, dt_fim)
        pag_raw    = client.get_contas_pagar(dt_ini, dt_fim)

        # Filtro pós-fetch: garante que só itens dentro do período passam
        def _dentro(item: dict) -> bool:
            venc = item.get("vencimento") or item.get("dataVencimento") or ""
            if not venc:
                return True  # sem data, deixa passar
            venc = str(venc)[:10]   # só YYYY-MM-DD
            return dt_ini <= venc <= dt_fim

        rec_raw = [it for it in rec_raw if _dentro(it)]
        pag_raw = [it for it in pag_raw if _dentro(it)]

        return {
            "vendas":         [BlingClient.normaliza_venda(v) for v in vendas_raw],
            "faturamento":    [BlingClient.normaliza_conta(v) for v in fat_raw],
            "contas_receber": [BlingClient.normaliza_conta(v) for v in rec_raw],
            "contas_pagar":   [BlingClient.normaliza_conta(v) for v in pag_raw],
        }
    except Exception as exc:
        st.error(f"Erro Bling: {exc}")
        return {"vendas": [], "faturamento": [], "contas_receber": [], "contas_pagar": []}


@st.cache_data(ttl=3600, show_spinner=False)
def load_bling_vendas_ano(ano: int) -> list:
    client = get_bling_client()
    if not client:
        return []
    try:
        from bling_api import BlingClient
        return [BlingClient.normaliza_venda(v) for v in client.get_vendas_ano(ano)]
    except Exception:
        return []


@st.cache_data(ttl=3600, show_spinner=False)
def load_bling_vencidas() -> dict:
    client = get_bling_client()
    if not client:
        return {"receber": [], "pagar": []}
    try:
        from bling_api import BlingClient
        return {
            "receber": [BlingClient.normaliza_conta(v) for v in client.get_vencidas_receber()],
            "pagar":   [BlingClient.normaliza_conta(v) for v in client.get_vencidas_pagar()],
        }
    except Exception:
        return {"receber": [], "pagar": []}


# ── Helpers unificados (eGestor + Bling) ──────────────────────────────────────

def get_empresas_disponiveis() -> list:
    """Retorna a lista de empresas disponíveis: sempre eGestor + Bling se conectado."""
    try:
        import bling_auth
        if bling_auth.is_connected():
            return NOMES + [NOME_YOU]
    except Exception:
        pass
    return list(NOMES)


def load_data_unificado(nome: str, dt_ini: str, dt_fim: str) -> dict:
    """Carrega dados de qualquer empresa (eGestor ou Bling)."""
    if nome == NOME_YOU:
        return load_bling_data(dt_ini, dt_fim)
    return load_company_data(nome, dt_ini, dt_fim)


def load_vendas_ano_unificado(nome: str, ano: int) -> list:
    """Carrega vendas anuais de qualquer empresa (eGestor ou Bling)."""
    if nome == NOME_YOU:
        return load_bling_vendas_ano(ano)
    return load_vendas_ano(nome, ano)


def load_vencidas_unificado(nome: str) -> dict:
    """Carrega contas vencidas de qualquer empresa (eGestor ou Bling)."""
    if nome == NOME_YOU:
        return load_bling_vencidas()
    return load_vencidas(nome)


# ── Realizado (despesas pagas) ────────────────────────────────────────────────

@st.cache_data(ttl=300, show_spinner=False)
def load_pagamentos_realizados(nome: str, dt_ini: str, dt_fim: str) -> list:
    """Carrega pagamentos efetivamente pagos (situFin=30) de uma empresa eGestor."""
    client = get_clients().get(nome)
    if not client:
        return []
    try:
        return client.get_pagamentos_realizados(dt_ini, dt_fim)
    except Exception as exc:
        st.error(f"Erro ao carregar realizados de {nome}: {exc}")
        return []


@st.cache_data(ttl=3600, show_spinner=False)
def load_realizados_12m(nome: str) -> list:
    """Carrega realizados dos últimos 12 meses (cache 1h)."""
    from datetime import date
    dt_fim = date.today()
    dt_ini = dt_fim.replace(year=dt_fim.year - 1)
    client = get_clients().get(nome)
    if not client:
        return []
    try:
        return client.get_pagamentos_realizados(
            dt_ini.strftime("%Y-%m-%d"), dt_fim.strftime("%Y-%m-%d")
        )
    except Exception:
        return []


@st.cache_data(ttl=300, show_spinner=False)
def load_bling_pagamentos_realizados(dt_ini: str, dt_fim: str) -> list:
    """Contas a pagar pagas do Bling, filtradas por data de pagamento."""
    client = get_bling_client()
    if not client:
        return []
    try:
        from bling_api import BlingClient
        raw = client.get_pagamentos_realizados(dt_ini, dt_fim)
        return [BlingClient.normaliza_pagamento_realizado(r) for r in raw]
    except Exception as exc:
        import streamlit as _st
        _st.error(f"Erro Bling realizados: {exc}")
        return []


@st.cache_data(ttl=3600, show_spinner=False)
def load_bling_realizados_12m() -> list:
    """Realizados Bling dos últimos 12 meses (cache 1h)."""
    from datetime import date
    dt_fim = date.today()
    dt_ini = dt_fim.replace(year=dt_fim.year - 1)
    return load_bling_pagamentos_realizados(
        dt_ini.strftime("%Y-%m-%d"), dt_fim.strftime("%Y-%m-%d")
    )


@st.cache_data(ttl=3600, show_spinner=False)
def load_plano_contas(nome: str) -> list:
    """Carrega plano de contas de uma empresa eGestor (cache 1h)."""
    client = get_clients().get(nome)
    if not client:
        return []
    try:
        return client.get_plano_contas()
    except Exception:
        return []
