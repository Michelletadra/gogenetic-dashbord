"""Página 6 — Sistema de Créditos de Clientes (dentro do dashboard financeiro).

A tela em si mora em `creditos_body.py`, compartilhada com o app independente
de Créditos (`creditos_app/app.py`). Aqui só entra o que é do dashboard:
configuração da página e o login do dashboard.
"""
import runpy
from pathlib import Path

import streamlit as st

from utils import GLOBAL_CSS, sidebar_header, require_auth

st.set_page_config(page_title="Créditos | GoGenetic", page_icon="💳", layout="wide")
st.markdown(GLOBAL_CSS, unsafe_allow_html=True)
sidebar_header()
require_auth()

runpy.run_path(str(Path(__file__).resolve().parent.parent / "creditos_body.py"),
               run_name="creditos_body")
