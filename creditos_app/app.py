"""App independente de Créditos — Grupo GoGenetic.

Sistema separado do dashboard financeiro, para entregar a um colaborador:
tem link e login próprios e mostra SÓ a gestão de créditos (nada de
faturamento, contas, contratos etc.). Usa o mesmo banco (Supabase) e a mesma
tela do dashboard (`creditos_body.py`) — o que for lançado aqui aparece lá
também, e vice-versa.

Deploy no Streamlit Community Cloud: mesmo repositório, "Main file path" =
`creditos_app/app.py`. Usuários ficam nos Secrets desse app (ver
creditos_app/README.md), separados dos usuários do dashboard.
"""
import copy
import runpy
import sys
from pathlib import Path

import streamlit as st

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

import streamlit_authenticator as stauth  # noqa: E402
from utils import GLOBAL_CSS, ASSETS  # noqa: E402

st.set_page_config(page_title="Créditos | Grupo GoGenetic", page_icon="💳",
                   layout="wide", initial_sidebar_state="expanded")
st.markdown(GLOBAL_CSS, unsafe_allow_html=True)
# Este app tem uma página só: esconde a navegação multipágina, se aparecer.
st.markdown("<style>[data-testid='stSidebarNav']{display:none}</style>", unsafe_allow_html=True)


def _usuarios() -> dict:
    """Usuários vêm SÓ dos Secrets deste app (bloco [creditos_usuarios]).
    Senha pode ser texto ou hash bcrypt — texto é convertido em hash na memória."""
    try:
        bruto = st.secrets["creditos_usuarios"]
    except Exception:
        return {}
    usuarios = {}
    for login, dados in dict(bruto).items():
        d = dict(dados)
        if d.get("password"):
            usuarios[str(login).strip().lower()] = {
                "name": d.get("name") or login,
                "email": d.get("email") or "",
                "password": str(d["password"]),
            }
    return usuarios


def _secret(key: str, default: str = "") -> str:
    try:
        return str(st.secrets.get(key, default))
    except Exception:
        return default


usuarios = _usuarios()
if not usuarios:
    st.error("🔒 Nenhum usuário configurado para o app de Créditos.")
    st.caption("Administrador: cadastre os usuários no bloco [creditos_usuarios] "
               "dos Secrets deste app (instruções em creditos_app/README.md).")
    st.stop()

if "_auth_creditos" not in st.session_state:
    st.session_state["_auth_creditos"] = stauth.Authenticate(
        {"usernames": copy.deepcopy(usuarios)},
        cookie_name="gogenetic_creditos_auth",
        cookie_key=_secret("CREDITOS_COOKIE_KEY", "gogenetic_creditos_cookie_key_padrao_2026"),
        cookie_expiry_days=30,
        auto_hash=True,
    )
authenticator = st.session_state["_auth_creditos"]

_estava_autenticado = bool(st.session_state.get("authentication_status"))
authenticator.login(location="main", fields={
    "Form name": "Créditos · Grupo GoGenetic", "Username": "Usuário",
    "Password": "Senha", "Login": "Entrar",
})
# Mesmo ajuste do dashboard (app.py): um rerun extra logo após o login pra
# garantir que o cookie de 30 dias seja gravado com credenciais em dict.
if st.session_state.get("authentication_status") and not _estava_autenticado:
    st.rerun()

if st.session_state.get("authentication_status") is False:
    st.error("❌ Usuário ou senha incorretos.")
    st.stop()
if not st.session_state.get("authentication_status"):
    st.markdown(
        "<p style='text-align:center;color:#7E16B8;font-weight:600;margin-top:24px'>"
        "Gestão de Créditos · Grupo GoGenetic</p>", unsafe_allow_html=True)
    st.stop()

with st.sidebar:
    st.image(str(ASSETS / "logo_gg.png"), use_container_width=True)
    st.markdown("<hr style='border:none;border-top:1px solid rgba(126,22,184,0.2);"
                "margin:12px 0 16px 0'>", unsafe_allow_html=True)
    st.caption(f"👤 {st.session_state.get('name', '')}")
    authenticator.logout("Sair", location="sidebar")

runpy.run_path(str(RAIZ / "creditos_body.py"), run_name="creditos_body")
