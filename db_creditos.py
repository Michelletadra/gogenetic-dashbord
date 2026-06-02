"""Roteador de banco — SQLite local ou Supabase na nuvem.
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
    # Tenta ler o backend
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
        import db_creditos_supabase as m
    else:
        import db_creditos_sqlite as m
    _mod = m
    return _mod

# ── Proxy de funções ──────────────────────────────────────────────────────────
def list_clientes(*a, **kw):       return _backend_mod().list_clientes(*a, **kw)
def get_cliente(*a, **kw):         return _backend_mod().get_cliente(*a, **kw)
def insert_cliente(*a, **kw):      return _backend_mod().insert_cliente(*a, **kw)
def update_cliente(*a, **kw):      return _backend_mod().update_cliente(*a, **kw)
def delete_cliente(*a, **kw):      return _backend_mod().delete_cliente(*a, **kw)
def resumo_cliente(*a, **kw):      return _backend_mod().resumo_cliente(*a, **kw)

def list_notas(*a, **kw):          return _backend_mod().list_notas(*a, **kw)
def get_nota(*a, **kw):            return _backend_mod().get_nota(*a, **kw)
def insert_nota(*a, **kw):         return _backend_mod().insert_nota(*a, **kw)
def update_nota(*a, **kw):         return _backend_mod().update_nota(*a, **kw)
def delete_nota(*a, **kw):         return _backend_mod().delete_nota(*a, **kw)

def list_creditos(*a, **kw):       return _backend_mod().list_creditos(*a, **kw)
def get_credito(*a, **kw):         return _backend_mod().get_credito(*a, **kw)
def insert_credito(*a, **kw):      return _backend_mod().insert_credito(*a, **kw)
def update_credito(*a, **kw):      return _backend_mod().update_credito(*a, **kw)
def delete_credito(*a, **kw):      return _backend_mod().delete_credito(*a, **kw)

def list_movimentacoes(*a, **kw):  return _backend_mod().list_movimentacoes(*a, **kw)
def insert_movimentacao(*a, **kw): return _backend_mod().insert_movimentacao(*a, **kw)
