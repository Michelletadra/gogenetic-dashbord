"""Cliente Bling API v3."""
import time
from datetime import date, timedelta
from typing import Optional

import requests

API = "https://api.bling.com.br/Api/v3"


class BlingClient:
    def __init__(self, access_token: str, company_name: str = "GoGenetic You"):
        self._token       = access_token
        self.company_name = company_name
        self._times: list = []

    def _rate_limit(self):
        now = time.time()
        self._times = [t for t in self._times if now - t < 1]
        if len(self._times) >= 3:
            time.sleep(0.4)
        self._times.append(time.time())

    def _get(self, endpoint: str, params: dict = None) -> dict:
        self._rate_limit()
        resp = requests.get(
            f"{API}/{endpoint}",
            headers={"Authorization": f"Bearer {self._token}", "Accept": "application/json"},
            params=params,
            timeout=20,
        )
        if resp.status_code == 429:
            time.sleep(10)
            return self._get(endpoint, params)
        resp.raise_for_status()
        return resp.json()

    def _pages(self, endpoint: str, params: dict = None) -> list:
        params = dict(params or {})
        result = []
        page = 1
        while True:
            params["pagina"] = page
            batch = self._get(endpoint, params).get("data", [])
            result.extend(batch)
            if len(batch) < 100:
                break
            page += 1
        return result

    # ── Vendas ────────────────────────────────────────────────────────────────

    def get_vendas(self, dt_ini: str, dt_fim: str) -> list:
        return self._pages("pedidos/vendas", {
            "dataInicial": dt_ini, "dataFinal": dt_fim, "idsSituacoes": "6,9",
        })

    def get_vendas_ano(self, ano: int) -> list:
        return self.get_vendas(f"{ano}-01-01", f"{ano}-12-31")

    # ── Financeiro ────────────────────────────────────────────────────────────

    def get_contas_receber(self, dt_ini: str, dt_fim: str) -> list:
        return self._pages("contas/receber", {
            "dataVencimentoInicial": dt_ini, "dataVencimentoFinal": dt_fim, "situacoes[]": 1,
        })

    def get_contas_pagar(self, dt_ini: str, dt_fim: str) -> list:
        return self._pages("contas/pagar", {
            "dataVencimentoInicial": dt_ini, "dataVencimentoFinal": dt_fim, "situacoes[]": 1,
        })

    def get_faturamento(self, dt_ini: str, dt_fim: str) -> list:
        return self._pages("contas/receber", {
            "dataVencimentoInicial": dt_ini, "dataVencimentoFinal": dt_fim, "situacoes[]": 2,
        })

    def get_pagamentos_realizados(self, dt_ini: str, dt_fim: str) -> list:
        return self._pages("contas/pagar", {
            "dataPagamentoInicial": dt_ini, "dataPagamentoFinal": dt_fim, "situacoes[]": 2,
        })

    def get_categorias(self) -> list:
        return self._pages("categorias/receitas-despesas")

    def get_vencidas_receber(self) -> list:
        ontem = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
        return self._pages("contas/receber", {
            "dataVencimentoInicial": "2020-01-01", "dataVencimentoFinal": ontem, "situacoes[]": 1,
        })

    def get_vencidas_pagar(self) -> list:
        ontem = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
        return self._pages("contas/pagar", {
            "dataVencimentoInicial": "2020-01-01", "dataVencimentoFinal": ontem, "situacoes[]": 1,
        })

    # ── Normalização ─────────────────────────────────────────────────────────

    @staticmethod
    def normaliza_venda(item: dict) -> dict:
        contato = item.get("contato") or {}
        return {
            "codigo":       item.get("numero") or item.get("id", ""),
            "dtVenda":      item.get("data", ""),
            "valorTotal":   item.get("totalVenda") or item.get("total", 0),
            "nomeContato":  contato.get("nome", ""),
            "nomeVendedor": (item.get("vendedor") or {}).get("nome", ""),
            "situacao":     (item.get("situacao") or {}).get("id", 0),
        }

    @staticmethod
    def normaliza_conta(item: dict) -> dict:
        contato = item.get("contato") or {}
        return {
            "codigo":      item.get("id", ""),
            "descricao":   item.get("descricao") or item.get("historico", ""),
            "valor":       item.get("valor", 0),
            "dtVenc":      item.get("vencimento") or item.get("dataVencimento", ""),
            "dtPgto":      item.get("dataPagamento", ""),
            "nomeContato": contato.get("nome", ""),
            "situacao":    (item.get("situacao") or {}).get("id", 0),
        }

    @staticmethod
    def normaliza_pagamento_realizado(item: dict, cat_map: dict = None) -> dict:
        contato  = item.get("contato") or {}
        cat_id   = (item.get("categoria") or {}).get("id")
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
            "nomeContato":     contato.get("nome", ""),
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
