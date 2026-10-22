"""Cliente Bling API v3.

Fase 1 (20/10/2026): chamadas passam por http_seguro.get_json (validação de
status/corpo/formato antes de decodificar, tentativas limitadas, erros
tipados). Falha nunca vira lista vazia: o erro sobe para quem chamou.
Limites oficiais (developer.bling.com.br/limites, consultado 19/10/2026):
3 req/s e 120 mil/dia por conta; GET com período > 1 ano retorna 400.
"""
import threading
import time
from datetime import date, timedelta
from typing import Callable, Optional

from http_seguro import ErroAutenticacao, ErroEsquema, exigir_lista, get_json

API = "https://api.bling.com.br/Api/v3"
LIMITE_PAGINA = 100          # máximo aceito pela API v3
MAX_PAGINAS = 500            # trava de segurança contra laço infinito
INTERVALO_MIN = 0.34         # ~3 requisições/segundo


def janelas_de_um_ano(dt_ini: str, dt_fim: str) -> list:
    """Quebra [dt_ini, dt_fim] em janelas de no máximo 1 ano (limite da API)."""
    ini = date.fromisoformat(dt_ini)
    fim = date.fromisoformat(dt_fim)
    out = []
    while ini <= fim:
        try:
            lim = ini.replace(year=ini.year + 1) - timedelta(days=1)
        except ValueError:          # 29/02
            lim = ini + timedelta(days=364)
        j_fim = min(lim, fim)
        out.append((ini.isoformat(), j_fim.isoformat()))
        ini = j_fim + timedelta(days=1)
    return out


class BlingClient:
    def __init__(self, access_token: str, company_name: str = "GoGenetic You",
                 renovar_token: Optional[Callable[[], Optional[str]]] = None,
                 _http_get=None, _dormir=time.sleep):
        self._token       = access_token
        self.company_name = company_name
        self._renovar     = renovar_token
        self._http_get    = _http_get
        self._dormir      = _dormir
        self._ultimo      = 0.0
        self._lock = threading.Lock()  # get_vendas/faturamento/contas_* rodam em paralelo

    def _rate_limit(self):
        with self._lock:
            espera = INTERVALO_MIN - (time.time() - self._ultimo)
            if espera > 0:
                self._dormir(espera)
            self._ultimo = time.time()

    def _get(self, endpoint: str, params: dict = None) -> dict:
        for tentativa in (1, 2):
            self._rate_limit()
            try:
                return get_json(
                    f"{API}/{endpoint}",
                    headers={"Authorization": f"Bearer {self._token}", "Accept": "application/json"},
                    params=params, provedor="Bling", empresa=self.company_name,
                    timeout=20, max_tentativas=3, dormir=self._dormir, http_get=self._http_get)
            except ErroAutenticacao:
                # Uma única renovação por chamada; se não resolver, o erro sobe.
                novo = self._renovar() if (self._renovar and tentativa == 1) else None
                if not novo:
                    raise
                self._token = novo

    def _pages(self, endpoint: str, params: dict = None) -> list:
        params = dict(params or {})
        params["limite"] = LIMITE_PAGINA
        result, vistos = [], set()
        for page in range(1, MAX_PAGINAS + 1):
            params["pagina"] = page
            batch = exigir_lista(self._get(endpoint, params), "data", provedor="Bling",
                                 empresa=self.company_name, endpoint=endpoint)
            for item in batch:
                chave = item.get("id") if isinstance(item, dict) else None
                if chave is not None:
                    if chave in vistos:
                        continue        # deduplica itens repetidos entre páginas
                    vistos.add(chave)
                result.append(item)
            if len(batch) < LIMITE_PAGINA:
                return result
        raise ErroEsquema(f"{endpoint}: mais de {MAX_PAGINAS} páginas — consulta interrompida por segurança",
                          provedor="Bling", empresa=self.company_name)

    def _pages_por_ano(self, endpoint: str, campo_ini: str, campo_fim: str,
                       dt_ini: str, dt_fim: str, extra: dict) -> list:
        """Mesma consulta, fatiada em janelas de até 1 ano (limite oficial)."""
        result, vistos = [], set()
        for j_ini, j_fim in janelas_de_um_ano(dt_ini, dt_fim):
            for item in self._pages(endpoint, {campo_ini: j_ini, campo_fim: j_fim, **extra}):
                chave = item.get("id") if isinstance(item, dict) else None
                if chave is not None and chave in vistos:
                    continue
                if chave is not None:
                    vistos.add(chave)
                result.append(item)
        return result

    # ── Vendas ────────────────────────────────────────────────────────────────

    def get_vendas(self, dt_ini: str, dt_fim: str) -> list:
        return self._pages_por_ano("pedidos/vendas", "dataInicial", "dataFinal",
                                   dt_ini, dt_fim, {"idsSituacoes": "6,9"})

    def get_vendas_ano(self, ano: int) -> list:
        return self.get_vendas(f"{ano}-01-01", f"{ano}-12-31")

    # ── Financeiro ────────────────────────────────────────────────────────────

    def get_contas_receber(self, dt_ini: str, dt_fim: str) -> list:
        return self._pages_por_ano("contas/receber", "dataVencimentoInicial", "dataVencimentoFinal",
                                   dt_ini, dt_fim, {"situacoes[]": 1})

    def get_contas_pagar(self, dt_ini: str, dt_fim: str) -> list:
        return self._pages_por_ano("contas/pagar", "dataVencimentoInicial", "dataVencimentoFinal",
                                   dt_ini, dt_fim, {"situacoes[]": 1})

    def get_faturamento(self, dt_ini: str, dt_fim: str) -> list:
        return self._pages_por_ano("contas/receber", "dataVencimentoInicial", "dataVencimentoFinal",
                                   dt_ini, dt_fim, {"situacoes[]": 2})

    def get_pagamentos_realizados(self, dt_ini: str, dt_fim: str) -> list:
        return self._pages_por_ano("contas/pagar", "dataPagamentoInicial", "dataPagamentoFinal",
                                   dt_ini, dt_fim, {"situacoes[]": 2})

    def get_categorias(self) -> list:
        return self._pages("categorias/receitas-despesas")

    def get_vencidas_receber(self) -> list:
        ontem = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
        return self._pages_por_ano("contas/receber", "dataVencimentoInicial", "dataVencimentoFinal",
                                   "2020-01-01", ontem, {"situacoes[]": 1})

    def get_vencidas_pagar(self) -> list:
        ontem = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
        return self._pages_por_ano("contas/pagar", "dataVencimentoInicial", "dataVencimentoFinal",
                                   "2020-01-01", ontem, {"situacoes[]": 1})

    # ── Normalização ─────────────────────────────────────────────────────────

    @staticmethod
    def _situacao_id(val) -> int:
        """A Bling v3 ora retorna 'situacao' como {'id': N}, ora como N direto."""
        if isinstance(val, dict):
            return val.get("id", 0)
        if isinstance(val, (int, float)):
            return int(val)
        return 0

    @staticmethod
    def normaliza_venda(item: dict) -> dict:
        contato = item.get("contato") or {}
        return {
            "codigo":       item.get("numero") or item.get("id", ""),
            "dtVenda":      item.get("data", ""),
            "valorTotal":   item.get("totalVenda") or item.get("total", 0),
            "nomeContato":  contato.get("nome", "") if isinstance(contato, dict) else "",
            "nomeVendedor": (item.get("vendedor") or {}).get("nome", "") if isinstance(item.get("vendedor"), dict) else "",
            "situacao":     BlingClient._situacao_id(item.get("situacao")),
        }

    @staticmethod
    def normaliza_conta(item: dict) -> dict:
        contato   = item.get("contato") or {}
        categoria = item.get("categoria")
        cat_id    = categoria.get("id") if isinstance(categoria, dict) else categoria
        return {
            "codigo":         item.get("id", ""),
            "descricao":      item.get("descricao") or item.get("historico", ""),
            "valor":          item.get("valor", 0),
            "dtVenc":         item.get("vencimento") or item.get("dataVencimento", ""),
            "dtPgto":         item.get("dataPagamento", ""),
            "nomeContato":    contato.get("nome", "") if isinstance(contato, dict) else "",
            "situacao":       BlingClient._situacao_id(item.get("situacao")),
            "codPlanoContas": cat_id,
        }

    @staticmethod
    def normaliza_pagamento_realizado(item: dict, cat_map: dict = None) -> dict:
        contato   = item.get("contato") or {}
        categoria = item.get("categoria")
        cat_id    = categoria.get("id") if isinstance(categoria, dict) else categoria
        historico = item.get("historico") or item.get("descricao") or ""
        if cat_map and cat_id and cat_id in cat_map:
            grupo    = cat_map[cat_id]["grupo"]
            subgrupo = cat_map[cat_id]["subgrupo"]
        else:
            grupo = subgrupo = historico or "Sem Categoria"
        return {
            "codigo":          item.get("id", ""),
            "descricao":       historico,
            "valor":           item.get("valor", 0),
            "dtPgto":          item.get("dataPagamento") or item.get("vencimento") or "",
            "dtVenc":          item.get("vencimento") or "",
            "nomeContato":     contato.get("nome", "") if isinstance(contato, dict) else "",
            "situacao":        2,
            "_grupo_bling":    grupo,
            "_subgrupo_bling": subgrupo,
        }

    @staticmethod
    def build_cat_map(categorias: list) -> dict:
        by_id = {c["id"]: c for c in categorias}

        def root(cid, depth=0):
            if depth > 8 or cid not in by_id:
                return "Sem Categoria"
            c = by_id[cid]
            pai = c.get("idCategoriaPai") or 0
            return root(pai, depth + 1) if pai else c.get("descricao", "Sem Categoria")

        result = {}
        for cid, c in by_id.items():
            pai = c.get("idCategoriaPai") or 0
            sub = c.get("descricao", "Sem Categoria")
            result[cid] = {"grupo": root(cid) if pai else sub, "subgrupo": sub}
        return result
