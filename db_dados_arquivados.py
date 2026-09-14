"""Roteador de banco — arquivo permanente de dados históricos (vendas,
faturamento, contas a receber/pagar) de períodos já fechados, que não mudam
mais. SQLite local ou Supabase na nuvem, mesmo padrão de lazy dispatch dos
outros roteadores deste projeto (db_creditos.py, db_contratos.py etc.).

Quem decide O QUE é "fechado" (e portanto arquivável pra sempre) é
utils.py — este módulo só sabe salvar e ler um blob de dados por
(empresa, chave)."""
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
        import db_dados_arquivados_supabase as m
    else:
        import db_dados_arquivados_sqlite as m
    _mod = m
    return _mod


def get_arquivado(empresa: str, chave: str):
    """Retorna os dados arquivados (já decodificados) ou None se ainda não
    foram arquivados."""
    try:
        return _backend_mod().get_arquivado(empresa, chave)
    except Exception:
        return None


def salvar_arquivado(empresa: str, chave: str, dados) -> None:
    """Salva dados como fechados/imutáveis. `dados` precisa ser algo
    JSON-serializável (list ou dict de tipos simples)."""
    try:
        _backend_mod().salvar_arquivado(empresa, chave, dados)
    except Exception:
        pass  # arquivamento é um otimização — se falhar, só busca de novo na próxima vez
