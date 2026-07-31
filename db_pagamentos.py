"""Roteador de banco — Gestão de Pagamentos (SQLite local ou Supabase na nuvem).
Usa lazy dispatch: backend decidido na primeira chamada (Streamlit já iniciado).
"""
import os
from dotenv import load_dotenv
load_dotenv()

_mod = None

def _backend_mod():
    global _mod
    if _mod is not None:
        return _mod
    supabase_url = os.getenv("SUPABASE_URL", "")
    if not supabase_url:
        try:
            import streamlit as st
            supabase_url = st.secrets["SUPABASE_URL"]
        except Exception:
            pass
    if supabase_url:
        import db_pagamentos_supabase as m
    else:
        import db_pagamentos_sqlite as m
    _mod = m
    return _mod


def list_contas_bancarias(*a, **kw):     return _backend_mod().list_contas_bancarias(*a, **kw)
def insert_conta_bancaria(*a, **kw):     return _backend_mod().insert_conta_bancaria(*a, **kw)
def update_conta_bancaria(*a, **kw):     return _backend_mod().update_conta_bancaria(*a, **kw)
def desativar_conta_bancaria(*a, **kw):  return _backend_mod().desativar_conta_bancaria(*a, **kw)

def insert_saldo(*a, **kw):              return _backend_mod().insert_saldo(*a, **kw)
def ultimos_saldos(*a, **kw):            return _backend_mod().ultimos_saldos(*a, **kw)
def historico_saldos(*a, **kw):          return _backend_mod().historico_saldos(*a, **kw)

def list_overrides(*a, **kw):            return _backend_mod().list_overrides(*a, **kw)
def upsert_override(*a, **kw):           return _backend_mod().upsert_override(*a, **kw)
def registrar_historico(*a, **kw):       return _backend_mod().registrar_historico(*a, **kw)
def historico_titulo(*a, **kw):          return _backend_mod().historico_titulo(*a, **kw)

def salvar_rodada(*a, **kw):             return _backend_mod().salvar_rodada(*a, **kw)
def list_rodadas(*a, **kw):              return _backend_mod().list_rodadas(*a, **kw)
