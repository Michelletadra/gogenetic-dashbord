"""Roteador de banco — SQLite local ou Supabase na nuvem."""
import os
from dotenv import load_dotenv
load_dotenv()

if os.getenv("DB_BACKEND", "sqlite") == "supabase":
    from db_creditos_supabase import *
else:
    from db_creditos_sqlite import *
