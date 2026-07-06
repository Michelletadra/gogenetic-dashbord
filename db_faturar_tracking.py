"""Rastreia a data em que cada serviço entrou em situação 'Faturar'.

A API do eGestor não guarda quando a situacaoOS mudou — só a data de
criação do orçamento/venda. Este módulo registra, no Supabase, a primeira
vez que cada serviço é visto com situacaoOS='Faturar', pra podermos medir
há quantos dias ele está parado nessa etapa.
"""
import os
from datetime import date
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


def sync(faturar_atual: dict, fora_de_faturar: set) -> dict:
    """
    faturar_atual: {codigo: cliente_nome} dos serviços hoje em 'Faturar'.
    fora_de_faturar: códigos que já não estão mais em 'Faturar' (limpeza).

    Retorna {codigo: data_entrada (str YYYY-MM-DD)} pros códigos em faturar_atual.
    """
    sb = _sb()
    hoje = date.today().isoformat()

    existentes = sb.table("faturar_tracking").select("codigo,data_entrada").execute().data
    datas = {e["codigo"]: e["data_entrada"] for e in existentes}

    novos = [
        {"codigo": cod, "data_entrada": hoje, "cliente_nome": nome}
        for cod, nome in faturar_atual.items()
        if cod not in datas
    ]
    if novos:
        sb.table("faturar_tracking").insert(novos).execute()
        for n in novos:
            datas[n["codigo"]] = n["data_entrada"]

    codigos_p_apagar = [c for c in fora_de_faturar if c in datas]
    if codigos_p_apagar:
        sb.table("faturar_tracking").delete().in_("codigo", codigos_p_apagar).execute()
        for c in codigos_p_apagar:
            datas.pop(c, None)

    return {cod: datas[cod] for cod in faturar_atual if cod in datas}
