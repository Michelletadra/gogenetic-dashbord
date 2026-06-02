"""Roteador de banco — SQLite local ou Supabase na nuvem.
Auto-detecta Supabase quando SUPABASE_URL estiver configurado.
"""
import os
from dotenv import load_dotenv
load_dotenv()

_backend = os.getenv("DB_BACKEND", "sqlite")
# Auto-usa Supabase se a URL estiver disponível (Streamlit Cloud secrets)
if _backend == "sqlite" and os.getenv("SUPABASE_URL"):
    _backend = "supabase"

if _backend == "supabase":
    from db_creditos_supabase import *
else:
    from db_creditos_sqlite import *
