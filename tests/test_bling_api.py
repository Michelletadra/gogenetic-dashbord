import json
from datetime import date

import pytest

from conftest import Resp
import bling_api
from bling_api import BlingClient, janelas_de_um_ano
from http_seguro import ErroAutenticacao, ErroEsquema, ErroFormato


class FakeBling:
    """Servidor Bling simulado: devolve itens por página e registra parâmetros."""
    def __init__(self, total=237, status_seq=None):
        self.total = total
        self.params = []
        self.status_seq = list(status_seq or [])
        self.tokens = []

    def __call__(self, url, headers=None, params=None, timeout=None):
        self.params.append(dict(params or {}))
        self.tokens.append(headers["Authorization"])
        if self.status_seq:
            st = self.status_seq.pop(0)
            if st != 200:
                return Resp(st, b'{"error":{"type":"x"}}')
        pg, lim = params.get("pagina", 1), params.get("limite", 100)
        ini = (pg - 1) * lim
        itens = [{"id": i, "valor": 1.5, "vencimento": "2026-10-01", "situacao": {"id": 1}}
                 for i in range(ini, min(ini + lim, self.total))]
        return Resp(200, json.dumps({"data": itens}))


def cliente(fake, **kw):
    return BlingClient("TOKEN1", "GoGenetic You", _http_get=fake, _dormir=lambda s: None, **kw)


def test_paginacao_completa_237_itens_em_3_paginas():
    fake = FakeBling(total=237)
    itens = cliente(fake).get_contas_receber("2026-01-01", "2026-10-20")
    assert len(itens) == 237 and len({i["id"] for i in itens}) == 237
    assert [p["pagina"] for p in fake.params] == [1, 2, 3]
    assert all(p["limite"] == 100 for p in fake.params)


def test_pagina_exata_de_100_busca_mais_uma():
    fake = FakeBling(total=200)
    assert len(cliente(fake).get_contas_pagar("2026-01-01", "2026-03-01")) == 200
    assert len(fake.params) == 3


def test_janelas_nunca_passam_de_um_ano():
    js = janelas_de_um_ano("2020-01-01", "2026-10-19")
    assert js[0] == ("2020-01-01", "2020-12-31") and js[-1][1] == "2026-10-19"
    for a, b in js:
        assert (date.fromisoformat(b) - date.fromisoformat(a)).days <= 365
    assert janelas_de_um_ano("2026-01-01", "2026-12-31") == [("2026-01-01", "2026-12-31")]
    assert janelas_de_um_ano("2024-02-29", "2025-03-01")[0] == ("2024-02-29", "2025-02-27")


def test_vencidas_em_fatias_de_ate_um_ano():
    fake = FakeBling(total=0)
    cliente(fake).get_vencidas_receber()
    for p in fake.params:
        a = date.fromisoformat(p["dataVencimentoInicial"])
        b = date.fromisoformat(p["dataVencimentoFinal"])
        assert (b - a).days <= 365          # antes: 2020→ontem numa chamada só (HTTP 400)
    assert fake.params[0]["dataVencimentoInicial"] == "2020-01-01"


def test_dedup_entre_janelas():
    fake = FakeBling(total=5)   # mesma lista em todas as janelas
    itens = cliente(fake).get_vencidas_pagar()
    assert len(itens) == 5


def test_401_renova_uma_vez_e_repete():
    fake = FakeBling(total=3, status_seq=[401, 200])
    renov = []
    c = cliente(fake, renovar_token=lambda: renov.append(1) or "TOKEN2")
    assert len(c.get_contas_receber("2026-10-01", "2026-10-20")) == 3
    assert renov == [1] and fake.tokens == ["Bearer TOKEN1", "Bearer TOKEN2"]


def test_401_persistente_sobe_erro_sem_laco():
    fake = FakeBling(total=3, status_seq=[401, 401, 401])
    c = cliente(fake, renovar_token=lambda: "TOKEN2")
    with pytest.raises(ErroAutenticacao):
        c.get_contas_receber("2026-10-01", "2026-10-20")
    assert len(fake.params) == 2


def test_sem_renovacao_disponivel():
    with pytest.raises(ErroAutenticacao):
        cliente(FakeBling(status_seq=[401])).get_contas_receber("2026-10-01", "2026-10-20")


def test_corpo_vazio_no_meio_da_paginacao_nao_vira_lista_parcial():
    chamadas = {"n": 0}
    def http_get(url, headers=None, params=None, timeout=None):
        chamadas["n"] += 1
        if params["pagina"] == 2:
            return Resp(200, b"")
        return Resp(200, json.dumps({"data": [{"id": i} for i in range(100)]}))
    with pytest.raises(ErroFormato):
        cliente(http_get).get_contas_receber("2026-01-01", "2026-10-20")


def test_esquema_inesperado():
    http_get = lambda *a, **k: Resp(200, json.dumps({"error": {"type": "VALIDATION_ERROR"}}))
    with pytest.raises(ErroEsquema):
        cliente(http_get).get_vendas("2026-10-01", "2026-10-20")


def test_trava_de_paginas(monkeypatch):
    monkeypatch.setattr(bling_api, "MAX_PAGINAS", 3)
    with pytest.raises(ErroEsquema):
        cliente(FakeBling(total=10_000)).get_contas_receber("2026-01-01", "2026-10-20")


def test_resultado_identico_ao_codigo_original_em_periodo_de_ate_um_ano(monkeypatch):
    """Regressão: no caminho de sucesso o cliente novo devolve exatamente o que o antigo devolvia."""
    import _bling_api_original as orig
    fake_novo, fake_velho = FakeBling(total=237), FakeBling(total=237)

    class R:  # adaptador: o cliente antigo chama requests.get diretamente
        @staticmethod
        def get(url, headers=None, params=None, timeout=None):
            p = dict(params); p.setdefault("limite", 100)
            return fake_velho(url, headers=headers, params=p, timeout=timeout)
    monkeypatch.setattr(orig, "requests", R)
    monkeypatch.setattr(orig.time, "sleep", lambda s: None)
    for metodo in ("get_vendas", "get_contas_receber", "get_contas_pagar", "get_faturamento"):
        a = getattr(cliente(fake_novo), metodo)("2026-01-01", "2026-10-20")
        b = getattr(orig.BlingClient("TOKEN1"), metodo)("2026-01-01", "2026-10-20")
        assert a == b, metodo
        assert [BlingClient.normaliza_conta(x) for x in a] == [orig.BlingClient.normaliza_conta(x) for x in b]
