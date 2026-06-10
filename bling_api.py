"""Cliente da API Bling v3."""
import time
from datetime import date, timedelta
from typing import Optional

import requests

API_URL = "https://www.bling.com.br/Api/v3"


class BlingClient:
    def __init__(self, access_token: str, company_name: str = "GoGenetic You"):
        self._token         = access_token
        self.company_name   = company_name
        self._request_times: list = []

    def _rate_limit(self):
        now = time.time()
        self._request_times = [t for t in self._request_times if now - t < 1]
        if len(self._request_times) >= 3:
            time.sleep(0.4)
        self._request_times.append(time.time())

    def _get(self, endpoint: str, params: Optional[dict] = None,
             _retry_auth: bool = True) -> dict:
        self._rate_limit()
        resp = requests.get(
            f"{API_URL}/{endpoint}",
            headers={
                "Authorization": f"Bearer {self._token}",
                "Accept":        "application/json",
            },
            params=params,
            timeout=20,
        )
        if resp.status_code == 429:
            time.sleep(10)
            return self._get(endpoint, params, _retry_auth=_retry_auth)
        if resp.status_code in (401, 403) and _retry_auth:
            # Token expirado/rejeitado → tenta renovar e repete uma vez
            try:
                import bling_auth as _ba
                new_token = _ba.get_valid_token(force_refresh=True)
                if new_token:
                    self._token = new_token
                    return self._get(endpoint, params, _retry_auth=False)
            except Exception:
                pass
        resp.raise_for_status()
        return resp.json()

    def _get_all_pages(self, endpoint: str, params: Optional[dict] = None) -> list:
        params   = dict(params or {})
        all_data: list = []
        page     = 1
        while True:
            params["pagina"] = page
            result = self._get(endpoint, params)
            batch  = result.get("data", [])
            all_data.extend(batch)
            if len(batch) < 100:   # Bling retorna até 100 por página
                break
            page += 1
        return all_data

    # ── Vendas ──────────────────────────────────────────────────────────────

    def get_vendas(self, dt_ini: str, dt_fim: str) -> list:
        """Pedidos de venda confirmados/atendidos."""
        return self._get_all_pages("pedidos/vendas", {
            "dataInicial":  dt_ini,
            "dataFinal":    dt_fim,
            "idsSituacoes": "6,9",   # 6=Em andamento, 9=Atendido
        })

    def get_vendas_ano(self, ano: int) -> list:
        return self.get_vendas(f"{ano}-01-01", f"{ano}-12-31")

    # ── Financeiro ──────────────────────────────────────────────────────────

    def get_contas_receber(self, dt_ini: str, dt_fim: str) -> list:
        return self._get_all_pages("contas/receber", {
            "dataVencimentoInicial": dt_ini,
            "dataVencimentoFinal":   dt_fim,
            "situacoes[]":           1,   # 1=Pendente
        })

    def get_contas_pagar(self, dt_ini: str, dt_fim: str) -> list:
        return self._get_all_pages("contas/pagar", {
            "dataVencimentoInicial": dt_ini,
            "dataVencimentoFinal":   dt_fim,
            "situacoes[]":           1,   # 1=Pendente
        })

    def get_faturamento(self, dt_ini: str, dt_fim: str) -> list:
        """Contas a receber já recebidas (faturamento realizado)."""
        return self._get_all_pages("contas/receber", {
            "dataVencimentoInicial": dt_ini,
            "dataVencimentoFinal":   dt_fim,
            "situacoes[]":           2,   # 2=Recebida
        })

    def get_pagamentos_realizados(self, dt_ini: str, dt_fim: str) -> list:
        """Contas a pagar já pagas, filtradas por data de pagamento."""
        return self._get_all_pages("contas/pagar", {
            "dataPagamentoInicial": dt_ini,
            "dataPagamentoFinal":   dt_fim,
            "situacoes[]":          2,    # 2=Pago
        })

    def get_categorias(self) -> list:
        """Retorna todas as categorias de receitas/despesas do Bling."""
        return self._get_all_pages("categorias/receitas-despesas")

    def get_pagamento_detalhe(self, pag_id: int) -> dict:
        """Retorna detalhe de uma conta a pagar (inclui categoria e historico)."""
        import time as _time
        _time.sleep(0.35)   # respeita rate limit ~3 req/s
        r = self._get(f"contas/pagar/{pag_id}")
        return r.get("data", {})

    def get_vencidas_receber(self) -> list:
        ontem = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
        return self._get_all_pages("contas/receber", {
            "dataVencimentoInicial": "2020-01-01",
            "dataVencimentoFinal":   ontem,
            "situacoes[]":           1,
        })

    def get_vencidas_pagar(self) -> list:
        ontem = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
        return self._get_all_pages("contas/pagar", {
            "dataVencimentoInicial": "2020-01-01",
            "dataVencimentoFinal":   ontem,
            "situacoes[]":           1,
        })

    # ── Normaliza para o formato padrão do dashboard ─────────────────────────

    @staticmethod
    def normaliza_venda(item: dict) -> dict:
        """Converte campo do Bling para o formato eGestor."""
        contato = item.get("contato") or {}
        return {
            "codigo":       item.get("numero") or item.get("id", ""),
            "dtVenda":      item.get("data", ""),
            "valorTotal":   item.get("totalVenda") or item.get("total", 0),
            "nomeContato":  contato.get("nome", ""),
            "nomeVendedor": item.get("vendedor", {}).get("nome", "") if item.get("vendedor") else "",
            "situacao":     item.get("situacao", {}).get("id", 0) if isinstance(item.get("situacao"), dict) else item.get("situacao", 0),
        }

    @staticmethod
    def normaliza_conta(item: dict) -> dict:
        """Converte conta (pagar/receber) do Bling para formato padrão."""
        contato = item.get("contato") or {}
        return {
            "codigo":      item.get("id", ""),
            "descricao":   item.get("descricao") or item.get("historico", ""),
            "valor":       item.get("valor", 0),
            "dtVenc":      item.get("vencimento") or item.get("dataVencimento", ""),
            "dtPgto":      item.get("dataPagamento", ""),
            "nomeContato": contato.get("nome", ""),
            "situacao":    item.get("situacao", {}).get("id", 0) if isinstance(item.get("situacao"), dict) else item.get("situacao", 0),
        }

    @staticmethod
    def normaliza_pagamento_realizado(item: dict, cat_map: dict = None) -> dict:
        """Converte conta/pagar paga do Bling para o formato do Realizado.
        Se cat_map (id → {grupo, subgrupo}) for fornecido, usa hierarquia real.
        """
        contato    = item.get("contato") or {}
        cat_id     = (item.get("categoria") or {}).get("id")
        historico  = item.get("historico") or item.get("descricao") or ""

        if cat_map and cat_id and cat_id in cat_map:
            grupo    = cat_map[cat_id]["grupo"]
            subgrupo = cat_map[cat_id]["subgrupo"]
        else:
            grupo    = historico or "Sem Categoria"
            subgrupo = historico or "Sem Categoria"

        return {
            "codigo":       item.get("id", ""),
            "descricao":    historico,
            "valor":        item.get("valor", 0),
            "dtPgto":       item.get("dataPagamento") or item.get("vencimento") or "",
            "dtVenc":       item.get("vencimento") or "",
            "nomeContato":  contato.get("nome", ""),
            "situacao":     2,
            "_grupo_bling":    grupo,
            "_subgrupo_bling": subgrupo,
        }

    @staticmethod
    def build_cat_map(categorias: list) -> dict:
        """Constrói mapa id → {grupo, subgrupo} a partir da lista de categorias."""
        by_id = {c["id"]: c for c in categorias}

        def root_nome(cid, depth=0):
            if depth > 8 or cid not in by_id:
                return "Sem Categoria"
            c = by_id[cid]
            pai = c.get("idCategoriaPai") or 0
            if not pai:
                return c.get("descricao", "Sem Categoria")
            return root_nome(pai, depth + 1)

        result = {}
        for cid, c in by_id.items():
            pai = c.get("idCategoriaPai") or 0
            sub = c.get("descricao", "Sem Categoria")
            grp = root_nome(cid) if pai else sub
            result[cid] = {"grupo": grp, "subgrupo": sub}
        return result
