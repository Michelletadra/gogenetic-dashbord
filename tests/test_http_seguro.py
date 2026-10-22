import json

import pytest
import requests

from conftest import Resp
from http_seguro import (ErroAutenticacao, ErroEsquema, ErroFormato, ErroLimite, ErroPermissao,
                         ErroRequisicao, ErroServidor, ErroTransporte, exigir_lista, get_json)


def chamar(respostas, **kw):
    fila = list(respostas)
    chamadas = []
    esperas = []

    def http_get(url, headers=None, params=None, timeout=None):
        chamadas.append(url)
        r = fila.pop(0)
        if isinstance(r, Exception):
            raise r
        return r

    try:
        return get_json("https://api.exemplo/v3/contas/receber", headers={"Authorization": "Bearer SEGREDO"},
                        provedor="Bling", empresa="GoGenetic You", http_get=http_get,
                        dormir=esperas.append, **kw), chamadas, esperas
    finally:
        chamar.ultimas = (chamadas, esperas)


def test_sucesso():
    dados, chamadas, _ = chamar([Resp(200, json.dumps({"data": [1, 2]}))])
    assert dados == {"data": [1, 2]} and len(chamadas) == 1


@pytest.mark.parametrize("resp,trecho", [
    (Resp(200, b""), "vazia"),
    (Resp(204, b"", ctype=""), "vazia"),
    (Resp(200, b"<html>manutencao</html>", ctype="text/html"), "HTML"),
    (Resp(200, b"<!DOCTYPE html><p>x", ctype="application/json"), "HTML"),
    (Resp(200, b'{"data":[{"id":1}', ctype="application/json"), "JSON"),
])
def test_corpo_invalido_vira_erro_de_formato_sem_repetir(resp, trecho):
    with pytest.raises(ErroFormato) as e:
        chamar([resp])
    assert trecho in str(e.value)
    assert len(chamar.ultimas[0]) == 1          # formato não é transitório
    assert "SEGREDO" not in str(e.value)


@pytest.mark.parametrize("status,classe", [(401, ErroAutenticacao), (403, ErroPermissao), (400, ErroRequisicao)])
def test_erros_definitivos_nao_repetem(status, classe):
    with pytest.raises(classe) as e:
        chamar([Resp(status, b'{"error":"x"}')] * 3)
    assert len(chamar.ultimas[0]) == 1
    assert e.value.status == status


def test_429_respeita_retry_after_e_depois_funciona():
    dados, chamadas, esperas = chamar([Resp(429, b"{}", headers={"Retry-After": "7"}),
                                       Resp(200, b'{"data":[]}')])
    assert dados == {"data": []} and len(chamadas) == 2 and esperas == [7.0]


def test_429_persistente_esgota_tentativas():
    with pytest.raises(ErroLimite):
        chamar([Resp(429, b"{}")] * 3, max_tentativas=3)
    chamadas, esperas = chamar.ultimas
    assert len(chamadas) == 3 and len(esperas) == 2      # espera progressiva entre tentativas
    assert esperas[1] > esperas[0]


def test_timeout_e_conexao_sao_transitorios():
    with pytest.raises(ErroTransporte):
        chamar([requests.exceptions.Timeout()] * 3)
    dados, chamadas, _ = chamar([requests.exceptions.ConnectionError(), Resp(200, b'{"ok":1}')])
    assert dados == {"ok": 1} and len(chamadas) == 2


def test_5xx_repete_e_recupera():
    dados, chamadas, _ = chamar([Resp(502, b"<html>bad gateway</html>", ctype="text/html"), Resp(200, b'{"a":1}')])
    assert dados == {"a": 1}
    with pytest.raises(ErroServidor):
        chamar([Resp(503, b"")] * 3)


def test_esquema():
    assert exigir_lista({"data": [1]}, "data", provedor="Bling") == [1]
    for ruim in ({"dados": []}, {"data": None}, {"data": {}}, [], "x"):
        with pytest.raises(ErroEsquema):
            exigir_lista(ruim, "data", provedor="Bling", endpoint="contas/receber")
