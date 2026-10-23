"""Smoke tests de tela (streamlit AppTest): a página abre, uma falha do Bling
não derruba nada e não aparece como R$ 0,00."""
import os

import pytest

pytest.importorskip("streamlit.testing.v1")
from streamlit.testing.v1 import AppTest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture
def utils_falhando(monkeypatch):
    import utils
    from http_seguro import ErroFormato
    utils._estado_integracoes.clear()

    def quebra(*a, **k):
        raise ErroFormato("resposta vazia de contas/receber (esperado JSON)", provedor="Bling",
                          empresa="GoGenetic You", status=200, correlacao="abc123")

    class FakeEg:
        def get_vendas(self, a, b): return [{"codigo": 1, "dtVenda": a, "valorTotal": 100.0}]
        def get_faturamento(self, a, b): return [{"codigo": 2, "valor": 50.0}]
        def get_contas_receber(self, a, b): return []
        def get_contas_pagar(self, a, b): return [{"codigo": 4, "valor": 5.0}]

    monkeypatch.setattr(utils, "get_bling_connection_error", lambda: None)
    monkeypatch.setattr(utils, "_cache_bling_data", quebra)
    monkeypatch.setattr(utils, "get_clients", lambda: {n: FakeEg() for n in utils.NOMES})
    return utils


def _logado(at):
    at.session_state["authentication_status"] = True
    at.session_state["username"] = "michelle"
    at.session_state["name"] = "Teste"
    return at


def test_pagina_you_com_bling_fora_do_ar(utils_falhando):
    at = _logado(AppTest.from_file(os.path.join(RAIZ, "pages", "10_You.py"), default_timeout=30)).run()
    assert not at.exception, at.exception
    textos = " ".join(e.value for e in at.error) + " ".join(w.value for w in at.warning)
    assert "não foi possível consultar" in textos.lower()
    assert "resposta vazia" in textos
    md = " ".join(m.value for m in at.markdown)
    assert "Recebido" not in md       # cartões de R$ 0,00 não são desenhados


def test_home_isola_falha_do_bling(utils_falhando):
    at = _logado(AppTest.from_file(os.path.join(RAIZ, "app.py"), default_timeout=30)).run()
    assert not at.exception, at.exception
    avisos = " ".join(w.value for w in at.warning)
    assert "GoGenetic You" in avisos and "NÃO significa ausência" in avisos
    md = " ".join(m.value for m in at.markdown)
    assert "GoGenetic Pesquisa" in md and "R$ 100,00" in md   # eGestor segue normal
    assert "consulta falhou" in md                             # selo só na empresa com falha


class FakeEgCompleto:
    def get_vendas(self, a, b): return [{"codigo": 1, "dtVenda": a, "valorTotal": 100.0, "nomeContato": "Cliente A",
                                         "nomeVendedor": "Vend", "situacao": 1}]
    def get_faturamento(self, a, b): return [{"codigo": 2, "valor": 50.0, "dtPgto": a, "nomeContato": "Cliente A"}]
    def get_contas_receber(self, a, b): return [{"codigo": 3, "valor": 7.0, "dtVenc": b, "nomeContato": "Cliente A", "descricao": "x"}]
    def get_contas_pagar(self, a, b): return [{"codigo": 4, "valor": 5.0, "dtVenc": b, "nomeContato": "Forn", "descricao": "y", "codPlanoContas": 1}]
    def get_vencidas_receber(self): return []
    def get_vencidas_pagar(self): return []
    def get_pagamentos_realizados(self, a, b): return [{"codigo": 9, "valor": 3.0, "dtPgto": b, "dtVenc": b,
                                                        "nomeContato": "Forn", "descricao": "z", "codPlanoContas": 1}]
    def get_plano_contas(self): return [{"codigo": 1, "nome": "Despesas", "codPai": 0}]
    def get_servicos(self, a, b): return [{"codigo": 10, "nomeContato": "Cliente A", "nomeVendedor": "Vend",
                                           "dtVenda": a, "dtEntrega": b, "valorTotal": 80.0,
                                           "situacaoOS": "Em execução", "tags": "S1234"}]


@pytest.mark.parametrize("pagina", ["1_Faturamento.py", "2_Vendas.py", "3_Contas.py", "4_Mensal.py",
                                    "7_Servicos.py", "8_Fluxo.py", "9_Realizado.py"])
# 7_Contratos.py e 6_Creditos.py não entram: dependem só do banco (não foram alterados na Fase 1)
# e o SQLite local de dev não tem as tabelas de clientes criadas fora do Supabase.
def test_paginas_abrem_sem_erro(pagina, monkeypatch, tmp_path):
    import utils
    utils._estado_integracoes.clear()
    import streamlit as st
    st.cache_data.clear()
    monkeypatch.setattr(utils, "get_bling_connection_error", lambda: "não conectado (teste)")
    monkeypatch.setattr(utils, "get_clients", lambda: {n: FakeEgCompleto() for n in utils.NOMES})
    at = _logado(AppTest.from_file(os.path.join(RAIZ, "pages", pagina), default_timeout=60)).run()
    assert not at.exception, [e.value for e in at.exception]
    assert not [w for w in at.warning if "não foi possível consultar" in w.value]


# ── Fase 2 ─────────────────────────────────────────────────────────────────────
from datetime import date as _date, timedelta as _td

_CTRS = [{"id": 1, "contratante": "Cliente Teste", "empresa_gg": "GG PESQUISA", "nome_contrato": "Teste",
          "valor_total": 300.0, "data_termino": "2027-12-31", "status_real": "ATIVO", "status": "ATIVO",
          "tipo_contrato": "P&D", "categoria": "Outro", "data_inicio": "2026-01-01", "moeda": "BRL",
          "servico_principal": "", "data_assinatura": "2026-01-01", "valor_recorrente": 0.0,
          "internacional": 0, "white_label": 0, "recorrente": 0, "renovacao_automatica": 0,
          "observacoes": "", "cnpj": "", "pais": "Brasil", "cliente_id": None, "total_parcelas": 2,
          "valor_parcela": 0.0, "responsavel_interno": "", "aviso_previo_dias": None}]


def _parcelas():
    d = (_date.today() + _td(days=10)).isoformat()
    return [{"id": 1, "contrato_id": 1, "numero": 1, "data_emissao": d, "valor": 123.45,
             "saldo_atual": 0, "situacao": "EM ESPERA", "numero_nf": None},
            {"id": 2, "contrato_id": 1, "numero": 2, "data_emissao": d, "valor": 100.0,
             "saldo_atual": 0, "situacao": "FATURADO", "numero_nf": "77"}]


def test_fluxo_usa_parcelas_do_banco_e_mostra_projecao(monkeypatch):
    import utils, db_contratos
    import streamlit as st
    utils._estado_integracoes.clear(); st.cache_data.clear()
    monkeypatch.setattr(utils, "get_bling_connection_error", lambda: "não conectado (teste)")
    monkeypatch.setattr(utils, "get_clients", lambda: {n: FakeEgCompleto() for n in utils.NOMES})
    monkeypatch.setattr(db_contratos, "list_contratos", lambda *a, **k: _CTRS)
    monkeypatch.setattr(db_contratos, "list_parcelas", lambda *a, **k: _parcelas())
    at = _logado(AppTest.from_file(os.path.join(RAIZ, "pages", "8_Fluxo.py"), default_timeout=60)).run()
    assert not at.exception, [e.value for e in at.exception]
    html = " ".join(m.value for m in at.markdown)
    assert "Projeção — próximas 13 semanas" in html
    assert "123,45" in html          # só a parcela pendente entra; a faturada (100) não
    assert "parcelas a faturar" in html


def test_contratos_aba_execucao(monkeypatch):
    import db_contratos, db_creditos
    monkeypatch.setattr(db_contratos, "list_contratos", lambda *a, **k: _CTRS)
    monkeypatch.setattr(db_contratos, "list_parcelas", lambda *a, **k: _parcelas())
    monkeypatch.setattr(db_contratos, "list_aditivos", lambda *a, **k: [])
    monkeypatch.setattr(db_contratos, "resumo_contratos", lambda *a, **k: {
        "qtd_ativos": 1, "qtd_vencidos": 0, "qtd_vencendo_30": 0, "qtd_vencendo_60": 0,
        "qtd_vencendo_90": 0, "qtd_encerrados": 0, "qtd_renovacao_auto": 0, "qtd_internacionais": 0,
        "qtd_white_label": 0, "qtd_recorrentes": 0, "receita_recorrente": 0.0,
        "valor_total_ativo": 300.0, "todos": _CTRS})
    monkeypatch.setattr(db_creditos, "list_clientes", lambda *a, **k: [])
    monkeypatch.setattr(db_creditos, "list_creditos", lambda *a, **k: [])
    at = _logado(AppTest.from_file(os.path.join(RAIZ, "pages", "7_Contratos.py"), default_timeout=60)).run()
    assert not at.exception, [e.value for e in at.exception]
    assert "📈 Execução" in [t.label for t in at.tabs]
    vals = {m.label: m.value for m in at.metric}
    assert "123,45" in vals["A faturar (parcelas)"] and "100,00" in vals["Faturado (parcelas)"]
