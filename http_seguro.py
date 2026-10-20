"""Chamadas HTTP de leitura com validação antes de decodificar JSON.

Usado pelos clientes Bling, Guru e Asaas (o cliente do eGestor continua como
está, por decisão de preservação). Objetivo: nunca transformar uma falha de
API em lista vazia/zero e nunca estourar um JSONDecodeError cru na tela.

- Valida status HTTP, Content-Type e corpo ANTES de decodificar.
- Erros tipados (transporte, autenticação, permissão, limite, formato,
  esquema, servidor, requisição) com mensagem em português.
- Tentativas limitadas com espera progressiva só para falhas transitórias
  (timeout/conexão, 429, 5xx). Autenticação/permissão/formato não repetem.
- Log com identificador de correlação, provedor e empresa — nunca token,
  cabeçalhos ou parâmetros sensíveis.
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Callable, Optional

import requests

log = logging.getLogger("integracoes")


class ErroIntegracao(Exception):
    """Base: falha ao consultar uma fonte externa (NÃO significa 'sem dados')."""
    transitorio = False

    def __init__(self, mensagem: str, *, provedor: str = "", empresa: str = "",
                 status: Optional[int] = None, correlacao: str = ""):
        super().__init__(mensagem)
        self.mensagem = mensagem
        self.provedor = provedor
        self.empresa = empresa
        self.status = status
        self.correlacao = correlacao

    def __str__(self) -> str:
        cod = f" (HTTP {self.status})" if self.status else ""
        ref = f" [ref {self.correlacao}]" if self.correlacao else ""
        return f"{self.provedor}: {self.mensagem}{cod}{ref}"


class ErroTransporte(ErroIntegracao):
    transitorio = True


class ErroLimite(ErroIntegracao):
    transitorio = True


class ErroServidor(ErroIntegracao):
    transitorio = True


class ErroAutenticacao(ErroIntegracao):
    pass


class ErroPermissao(ErroIntegracao):
    pass


class ErroRequisicao(ErroIntegracao):
    pass


class ErroFormato(ErroIntegracao):
    pass


class ErroEsquema(ErroIntegracao):
    pass


def _resumo_corpo(resp) -> str:
    """Trecho curto e seguro do corpo para log/mensagem (sem quebrar linhas)."""
    try:
        txt = (resp.text or "")[:160]
    except Exception:
        return ""
    return " ".join(txt.split())


def _espera(tentativa: int, resp=None, base: float = 2.0, teto: float = 30.0) -> float:
    if resp is not None:
        ra = (resp.headers or {}).get("Retry-After")
        if ra:
            try:
                return min(float(ra), teto)
            except ValueError:
                pass
    return min(base * (2 ** (tentativa - 1)), teto)


def get_json(url: str, *, headers: dict, params=None, provedor: str, empresa: str = "",
             timeout: float = 20, max_tentativas: int = 3,
             dormir: Callable[[float], None] = time.sleep,
             http_get: Callable = None) -> dict | list:
    """GET que devolve JSON já validado ou levanta ErroIntegracao.

    `dormir` e `http_get` existem para os testes (sem rede, sem espera real).
    """
    http_get = http_get or requests.get
    correlacao = uuid.uuid4().hex[:8]
    ctx = dict(provedor=provedor, empresa=empresa, correlacao=correlacao)
    endpoint = url.split("?")[0].rsplit("/", 2)[-2:]
    endpoint = "/".join(endpoint)

    ultimo: Optional[ErroIntegracao] = None
    for tentativa in range(1, max_tentativas + 1):
        resp = None
        try:
            resp = http_get(url, headers=headers, params=params, timeout=timeout)
        except requests.exceptions.Timeout:
            ultimo = ErroTransporte(f"tempo esgotado ({timeout:.0f}s) ao consultar {endpoint}", **ctx)
        except requests.exceptions.RequestException as e:
            ultimo = ErroTransporte(f"falha de conexão ao consultar {endpoint} ({type(e).__name__})", **ctx)
        else:
            st_code = resp.status_code
            if st_code == 429:
                ultimo = ErroLimite("limite de requisições da API atingido", status=429, **ctx)
            elif st_code >= 500:
                ultimo = ErroServidor(f"API indisponível no momento ({endpoint})", status=st_code, **ctx)
            elif st_code == 401:
                raise _log(ErroAutenticacao("token inválido ou expirado — é preciso renovar/reconectar",
                                            status=401, **ctx), endpoint, resp)
            elif st_code == 403:
                raise _log(ErroPermissao("acesso negado (permissão/escopo insuficiente ou IP bloqueado)",
                                         status=403, **ctx), endpoint, resp)
            elif st_code >= 400:
                raise _log(ErroRequisicao(f"requisição recusada pela API: {_resumo_corpo(resp)}",
                                          status=st_code, **ctx), endpoint, resp)
            else:
                return _decodificar(resp, endpoint, ctx)

        _log(ultimo, endpoint, resp, nivel=logging.WARNING, tentativa=tentativa)
        if tentativa < max_tentativas:
            dormir(_espera(tentativa, resp))
    raise ultimo


def _decodificar(resp, endpoint: str, ctx: dict):
    corpo = resp.content or b""
    if resp.status_code == 204 or not corpo.strip():
        raise _log(ErroFormato(f"resposta vazia de {endpoint} (esperado JSON)",
                               status=resp.status_code, **ctx), endpoint, resp)
    ctype = ((resp.headers or {}).get("Content-Type") or "").lower()
    if "html" in ctype or corpo.lstrip()[:1] == b"<":
        raise _log(ErroFormato(f"a API devolveu uma página HTML em vez de dados ({endpoint}) — "
                               f"possível manutenção, bloqueio ou endereço incorreto",
                               status=resp.status_code, **ctx), endpoint, resp)
    try:
        return json.loads(corpo.decode(resp.encoding or "utf-8", errors="replace"))
    except ValueError:
        raise _log(ErroFormato(f"resposta de {endpoint} não é um JSON válido (corpo truncado ou corrompido)",
                               status=resp.status_code, **ctx), endpoint, resp)


def _log(erro: ErroIntegracao, endpoint: str, resp=None, nivel=logging.ERROR, tentativa=None):
    ctype = ""
    if resp is not None:
        ctype = ((resp.headers or {}).get("Content-Type") or "")[:40]
    log.log(nivel, "integracao_falha ref=%s provedor=%s empresa=%s endpoint=%s status=%s "
                   "content_type=%s tipo=%s tentativa=%s",
            erro.correlacao, erro.provedor, erro.empresa, endpoint, erro.status, ctype,
            type(erro).__name__, tentativa)
    return erro


def exigir_lista(dados, campo: str, *, provedor: str, empresa: str = "", endpoint: str = "") -> list:
    """Valida o esquema mínimo {campo: [...]} e devolve a lista."""
    if not isinstance(dados, dict) or campo not in dados or not isinstance(dados[campo], list):
        chaves = list(dados.keys())[:5] if isinstance(dados, dict) else type(dados).__name__
        raise ErroEsquema(f"formato inesperado em {endpoint}: esperado '{campo}' como lista, recebido {chaves}",
                          provedor=provedor, empresa=empresa)
    return dados[campo]
