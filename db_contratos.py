"""Roteador de banco — contratos (SQLite local ou Supabase na nuvem).
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
    backend = os.getenv("DB_BACKEND", "")
    if not backend:
        try:
            import streamlit as st
            backend = st.secrets.get("DB_BACKEND", "")
            if not backend and st.secrets.get("SUPABASE_URL"):
                backend = "supabase"
        except Exception:
            pass
    if not backend and os.getenv("SUPABASE_URL"):
        backend = "supabase"

    if backend == "supabase":
        import db_contratos_supabase as m
    else:
        import db_contratos_sqlite as m
    _mod = m
    return _mod

# ── Proxy de funções ──────────────────────────────────────────────────────────
def list_contratos(*a, **kw):      return _backend_mod().list_contratos(*a, **kw)
def get_contrato(*a, **kw):        return _backend_mod().get_contrato(*a, **kw)
def insert_contrato(*a, **kw):     return _backend_mod().insert_contrato(*a, **kw)
def update_contrato(*a, **kw):     return _backend_mod().update_contrato(*a, **kw)
def delete_contrato(*a, **kw):     return _backend_mod().delete_contrato(*a, **kw)
def list_parcelas(*a, **kw):       return _backend_mod().list_parcelas(*a, **kw)
def insert_parcela(*a, **kw):      return _backend_mod().insert_parcela(*a, **kw)
def update_parcela(*a, **kw):      return _backend_mod().update_parcela(*a, **kw)
def delete_parcela(*a, **kw):      return _backend_mod().delete_parcela(*a, **kw)
