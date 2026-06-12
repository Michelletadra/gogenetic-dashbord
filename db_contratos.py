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
    # Prefere Supabase se a URL estiver disponível (env ou st.secrets)
    supabase_url = os.getenv("SUPABASE_URL", "")
    _debug = f"env={bool(supabase_url)}"
    if not supabase_url:
        try:
            import streamlit as st
            supabase_url = st.secrets["SUPABASE_URL"]
            _debug += f" secrets=OK url={supabase_url[:20]}"
        except Exception as _e:
            _debug += f" secrets_err={_e}"
    try:
        import streamlit as st
        st.session_state["_db_debug"] = _debug
    except Exception:
        pass
    if supabase_url:
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
def list_aditivos(*a, **kw):       return _backend_mod().list_aditivos(*a, **kw)
def insert_aditivo(*a, **kw):      return _backend_mod().insert_aditivo(*a, **kw)
def delete_aditivo(*a, **kw):      return _backend_mod().delete_aditivo(*a, **kw)
def resumo_contratos(*a, **kw):    return _backend_mod().resumo_contratos(*a, **kw)
def compute_status(*a, **kw):      return _backend_mod().compute_status(*a, **kw)
