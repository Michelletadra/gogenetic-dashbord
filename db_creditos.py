"""Roteador de banco — SQLite local ou Supabase na nuvem."""
import os
from dotenv import load_dotenv
load_dotenv()

def _get_backend() -> str:
    # 1. variável de ambiente (.env local)
    val = os.getenv("DB_BACKEND", "")
    if val:
        return val
    # 2. Streamlit secrets (Streamlit Cloud)
    try:
        import streamlit as st
        val = st.secrets.get("DB_BACKEND", "")
        if val:
            return val
        # Se SUPABASE_URL estiver nos secrets, usa Supabase
        if st.secrets.get("SUPABASE_URL"):
            return "supabase"
    except Exception:
        pass
    # 3. Se SUPABASE_URL estiver no env, usa Supabase
    if os.getenv("SUPABASE_URL"):
        return "supabase"
    return "sqlite"

if _get_backend() == "supabase":
    from db_creditos_supabase import *
else:
    from db_creditos_sqlite import *
