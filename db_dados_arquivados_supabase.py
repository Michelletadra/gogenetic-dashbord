"""Backend Supabase (produção) — arquivo de dados históricos.

Tabela `dados_arquivados` (chave primária composta empresa+chave, coluna
`dados` jsonb) guarda pra sempre o resultado de uma consulta de período já
fechado (ano anterior ao ano corrente): vendas de um ano inteiro, ou o
pacote de 4 endpoints (vendas/faturamento/contas a receber/contas a pagar)
de um intervalo de datas que já terminou antes do ano corrente começar.
Ver sql_dados_arquivados.sql para o DDL (rodar uma vez no Supabase SQL
Editor antes de usar em produção)."""
import os
from supabase import create_client


def _secret(key: str) -> str:
    val = os.getenv(key, "")
    if not val:
        try:
            import streamlit as st
            val = st.secrets.get(key, "")
        except Exception:
            pass
    return val


_CLIENT = None


def _sb():
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = create_client(_secret("SUPABASE_URL"), _secret("SUPABASE_KEY"))
    return _CLIENT


def get_arquivado(empresa: str, chave: str):
    rows = (
        _sb().table("dados_arquivados")
        .select("dados")
        .eq("empresa", empresa)
        .eq("chave", chave)
        .execute()
        .data
    )
    if not rows:
        return None
    return rows[0]["dados"]


def salvar_arquivado(empresa: str, chave: str, dados) -> None:
    _sb().table("dados_arquivados").upsert({
        "empresa": empresa,
        "chave": chave,
        "dados": dados,
    }).execute()
