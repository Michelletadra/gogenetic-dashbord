"""Roteador de banco — contratos (SQLite local ou Supabase na nuvem)."""
import os
from dotenv import load_dotenv
load_dotenv()

if os.getenv("DB_BACKEND", "sqlite") == "supabase":
    from db_contratos_supabase import *
else:
    from db_contratos_sqlite import *
