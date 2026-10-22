import threading
import time
from datetime import datetime, timedelta, timezone

import pytest

from conftest import Resp
import bling_auth


# ── Token ────────────────────────────────────────────────────────────────────

def test_json_token_rejeita_html_vazio_e_sem_token():
    for r in (Resp(200, b"<html>login</html>", ctype="text/html"), Resp(200, b""),
              Resp(200, b'{"x":1}'), Resp(200, b'{"access_token":')):
        with pytest.raises(RuntimeError):
            bling_auth._json_token(r)
    assert bling_auth._json_token(Resp(200, b'{"access_token":"a","refresh_token":"b"}'))["access_token"] == "a"


def test_enable_jwt_so_quando_ligado(monkeypatch):
    monkeypatch.setenv("BLING_CLIENT_ID", "id"); monkeypatch.setenv("BLING_CLIENT_SECRET", "s")
    monkeypatch.delenv("BLING_ENABLE_JWT", raising=False)
    assert "enable-jwt" not in bling_auth._headers_token()
    monkeypatch.setenv("BLING_ENABLE_JWT", "1")
    assert bling_auth._headers_token()["enable-jwt"] == "1"


def test_renovacoes_simultaneas_viram_uma_so(monkeypatch):
    """10 threads pedem token expirado ao mesmo tempo: só 1 refresh é feito."""
    banco = {"access_token": "velho", "refresh_token": "r1",
             "expires_at": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()}
    refreshes = []

    def fake_refresh(rt):
        refreshes.append(rt)
        time.sleep(0.05)
        banco.update(access_token="novo", refresh_token="r2",
                     expires_at=(datetime.now(timezone.utc) + timedelta(hours=6)).isoformat())
        return "novo"

    monkeypatch.setattr(bling_auth, "_load", lambda: dict(banco))
    monkeypatch.setattr(bling_auth, "_refresh", fake_refresh)
    res = []
    ts = [threading.Thread(target=lambda: res.append(bling_auth.get_token())) for _ in range(10)]
    [t.start() for t in ts]; [t.join() for t in ts]
    assert refreshes == ["r1"] and res == ["novo"] * 10


def test_falha_ao_gravar_token_fica_visivel(monkeypatch, tmp_path):
    def sb_quebrado():
        raise ConnectionError("supabase fora")
    monkeypatch.setattr(bling_auth, "_sb", sb_quebrado)
    monkeypatch.setattr(bling_auth, "TOKEN_FILE", tmp_path / "t.json")
    bling_auth._save({"access_token": "a", "refresh_token": "b", "expires_in": 60})
    assert "não gravado" in bling_auth.aviso_persistencia()


# ── Cargas no utils: falha ≠ zero ────────────────────────────────────────────

@pytest.fixture
def u():
    import utils
    utils._estado_integracoes.clear()
    import streamlit as st
    st.cache_data.clear()
    return utils


def test_falha_nao_vira_zero_silencioso(u):
    def quebra():
        raise RuntimeError("Bling: resposta vazia de contas/receber")
    r = u._executar("GoGenetic You", "periodo:a:b", quebra, {"vendas": []})
    assert r == {"vendas": []}
    f = u.falhas_integracao(["GoGenetic You"])
    assert len(f) == 1 and "resposta vazia" in f[0]["erro"] and f[0]["ultimo_ok_em"] is None
    assert u.empresa_com_falha("GoGenetic You") and not u.empresa_com_falha("GoSolos")


def test_falha_devolve_ultima_resposta_valida(u, monkeypatch):
    u._executar("GoSolos", "k", lambda: {"vendas": [{"v": 1}]}, {})
    monkeypatch.setattr(u, "ESPERA_APOS_FALHA", 0)
    r = u._executar("GoSolos", "k", lambda: (_ for _ in ()).throw(TimeoutError()), {})
    assert r == {"vendas": [{"v": 1}]}
    assert u.falhas_integracao()[0]["ultimo_ok_em"] is not None


def test_nao_martela_api_logo_apos_falha(u):
    n = {"c": 0}
    def quebra():
        n["c"] += 1
        raise RuntimeError("x")
    for _ in range(5):
        u._executar("GoGenetic Pesquisa", "k", quebra, [])
    assert n["c"] == 1


def test_falha_de_uma_empresa_nao_afeta_outra(u):
    u._executar("GoGenetic You", "k", lambda: (_ for _ in ()).throw(RuntimeError("bling fora")), [])
    assert u._executar("GoGenetic Pesquisa", "k", lambda: [1, 2], []) == [1, 2]
    assert [f["empresa"] for f in u.falhas_integracao()] == ["GoGenetic You"]


def test_sucesso_identico_ao_codigo_original_egestor(u, monkeypatch):
    """Regressão eGestor: mesmo cliente simulado → mesmo resultado que a versão a1d00c7."""
    import _utils_original as orig

    class FakeEg:
        def get_vendas(self, a, b): return [{"codigo": 1, "dtVenda": a, "valorTotal": 10.5}]
        def get_faturamento(self, a, b): return [{"codigo": 2, "valor": 3}]
        def get_contas_receber(self, a, b): return [{"codigo": 3, "valor": 4}]
        def get_contas_pagar(self, a, b): return [{"codigo": 4, "valor": 5}]
        def get_vencidas_receber(self): return [{"codigo": 5}]
        def get_vencidas_pagar(self): return [{"codigo": 6}]
    fake = {"GoGenetic Pesquisa": FakeEg()}
    monkeypatch.setattr(u, "get_clients", lambda: fake)
    monkeypatch.setattr(orig, "get_clients", lambda: fake)
    assert u.load_company_data("GoGenetic Pesquisa", "2026-10-01", "2026-10-20") == \
        orig.load_company_data("GoGenetic Pesquisa", "2026-10-01", "2026-10-20")
    assert u.load_vencidas("GoGenetic Pesquisa") == orig.load_vencidas("GoGenetic Pesquisa")
    assert u.load_vendas_ano("GoGenetic Pesquisa", 2026) == orig.load_vendas_ano("GoGenetic Pesquisa", 2026)
    assert u.falhas_integracao() == []


# ── Créditos: chave de segurança da baixa automática ─────────────────────────

def test_baixa_automatica_desligada_nao_le_nem_grava(monkeypatch):
    import creditos_sync
    monkeypatch.setenv("CREDITOS_AUTO_BAIXA", "0")

    class Explode:
        def get_servicos(self, *a):
            raise AssertionError("não deveria consultar o eGestor com a chave desligada")
    r = creditos_sync.sincronizar({"GoGenetic Pesquisa": Explode()}, dias=365)
    assert r["baixados"] == 0 and "desligada" in r["erros"][0]


def test_baixa_automatica_ligada_por_padrao(monkeypatch):
    import creditos_sync
    monkeypatch.delenv("CREDITOS_AUTO_BAIXA", raising=False)
    assert creditos_sync.baixa_automatica_ligada() is True
