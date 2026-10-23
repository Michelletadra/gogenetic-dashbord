"""Separação de impostos em A Pagar / Vencidos pelo plano de contas. Dados simulados."""
import os
import pytest
import impostos as imp

PLANO = [
    {"codigo": 1, "nome": "Despesas operacionais", "codPai": 0},
    {"codigo": 2, "nome": "FGTS", "codPai": 1},
    {"codigo": 10, "nome": "Impostos", "codPai": 0},
    {"codigo": 11, "nome": "DAS MEI/SIMPLES Terceiros", "codPai": 10},
    {"codigo": 12, "nome": "ISS RETIDO NA FONTE", "codPai": 10},
    {"codigo": 13, "nome": "Federais", "codPai": 10},
    {"codigo": 14, "nome": "PIS", "codPai": 13},          # neto do grupo Impostos
]


def test_separa_pelo_grupo_do_plano_e_por_empresa():
    info = {"A": imp.plano_info(PLANO), "B": imp.plano_info([{"codigo": 11, "nome": "Aluguel", "codPai": 0}])}
    itens = [
        {"empresa": "A", "valor": 100, "codPlanoContas": 11},
        {"empresa": "A", "valor": 50, "codPlanoContas": "14"},
        {"empresa": "A", "valor": 30, "codPlanoContas": 2},   # FGTS fica em Despesas operacionais
        {"empresa": "A", "valor": 7, "codPlanoContas": None},  # sem conta: não é imposto
        {"empresa": "B", "valor": 9, "codPlanoContas": 11},    # mesmo código, outra empresa: Aluguel
        {"empresa": "GoGenetic You", "valor": 1},
    ]
    demais, impostos = imp.separar(itens, info)
    assert [i["valor"] for i in impostos] == [100, 50]
    assert [i["tipo_imposto"] for i in impostos] == ["DAS MEI/SIMPLES Terceiros", "PIS"]
    assert [i["valor"] for i in demais] == [30, 7, 9, 1]
    assert sum(i["valor"] for i in demais + impostos) == sum(i["valor"] for i in itens)  # nada some


def test_grupo_tributos_e_variacoes():
    assert imp.grupo_e_imposto("Impostos e Taxas")
    assert imp.grupo_e_imposto("TRIBUTOS")
    assert imp.grupo_e_imposto("Tributário")
    assert not imp.grupo_e_imposto("Despesas diversas")


pytest.importorskip("streamlit.testing.v1")
from streamlit.testing.v1 import AppTest
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class FakeEgImp:
    def get_vendas(self, a, b): return []
    def get_faturamento(self, a, b): return []
    def get_contas_receber(self, a, b): return []
    def get_contas_pagar(self, a, b): return [
        {"codigo": 1, "valor": 500.0, "dtVenc": b, "nomeContato": "Forn", "descricao": "aluguel", "codPlanoContas": 2},
        {"codigo": 2, "valor": 123.45, "dtVenc": b, "nomeContato": "Receita", "descricao": "DAS", "codPlanoContas": 11}]
    def get_vencidas_receber(self): return []
    def get_vencidas_pagar(self): return [
        {"codigo": 3, "valor": 67.89, "dtVenc": "2026-01-10", "nomeContato": "Prefeitura", "descricao": "ISS",
         "codPlanoContas": 12}]
    def get_plano_contas(self): return PLANO


def test_tela_contas_separa_impostos(monkeypatch):
    import utils
    import streamlit as st
    utils._estado_integracoes.clear(); st.cache_data.clear()
    monkeypatch.setattr(utils, "get_bling_connection_error", lambda: "não conectado (teste)")
    monkeypatch.setattr(utils, "get_clients", lambda: {n: FakeEgImp() for n in utils.NOMES})
    at = AppTest.from_file(os.path.join(RAIZ, "pages", "3_Contas.py"), default_timeout=60)
    at.session_state["authentication_status"] = True
    at.session_state["username"] = "michelle"; at.session_state["name"] = "Teste"
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    md = " ".join(m.value for m in at.markdown)
    n = len(utils.NOMES)
    assert f"🧾" in md and "Impostos" in md
    assert utils.brl(500.0 * n) in md           # A Pagar sem impostos
    assert utils.brl(123.45 * n) in md          # Impostos a vencer
    assert utils.brl(67.89 * n) in md           # Impostos em atraso
    assert any(t.label.startswith("🧾 Impostos (") for t in at.tabs)
