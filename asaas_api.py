"""Cliente da API do Asaas (cobranças/pagamentos da GoGenetic You)."""
import time
from datetime import date, timedelta

from http_seguro import ErroEsquema, exigir_lista, get_json

API = "https://api.asaas.com/v3"

STATUS_RECEBIDO = ("RECEIVED", "CONFIRMED", "RECEIVED_IN_CASH")
STATUS_PENDENTE = ("PENDING", "AWAITING_RISK_ANALYSIS")


class AsaasClient:
    def __init__(self, api_key: str, _http_get=None, _dormir=time.sleep):
        self._key = api_key
        self._http_get = _http_get
        self._dormir = _dormir

    def _get(self, endpoint: str, params: dict = None) -> dict:
        return get_json(f"{API}/{endpoint}",
                        headers={"access_token": self._key, "User-Agent": "GoGeneticDashboard",
                                 "Content-Type": "application/json", "Accept": "application/json"},
                        params=params, provedor="Asaas", empresa="GoGenetic You",
                        timeout=20, max_tentativas=3, http_get=self._http_get, dormir=self._dormir)

    def _pages(self, endpoint: str, params: dict = None) -> list:
        params = dict(params or {})
        result = []
        offset = 0
        limit = 100
        for _ in range(2000):   # trava contra paginação infinita
            params.update({"offset": offset, "limit": limit})
            data = self._get(endpoint, params)
            batch = exigir_lista(data, "data", provedor="Asaas", endpoint=endpoint)
            result.extend(batch)
            if not data.get("hasMore"):
                return result
            offset += limit
        raise ErroEsquema(f"{endpoint}: paginação não terminou", provedor="Asaas")

    # ── Clientes (usado só pra montar o mapa id -> nome) ─────────────────────
    def get_customers_map(self) -> dict:
        customers = self._pages("customers")
        return {c["id"]: c.get("name", "") for c in customers}

    # ── Cobranças ─────────────────────────────────────────────────────────────
    def get_contas_receber(self, dt_ini: str, dt_fim: str) -> list:
        """Cobranças com vencimento no período, independente de pagas ou não."""
        return self._pages("payments", {
            "dueDate[ge]": dt_ini, "dueDate[le]": dt_fim,
        })

    def get_recebidos(self, dt_ini: str, dt_fim: str) -> list:
        """Cobranças efetivamente pagas/recebidas no período (fluxo de caixa)."""
        return self._pages("payments", {
            "paymentDate[ge]": dt_ini, "paymentDate[le]": dt_fim,
            "status[]": list(STATUS_RECEBIDO),
        })

    def get_vencidas(self) -> list:
        ontem = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
        return self._pages("payments", {
            "dueDate[le]": ontem, "status": "OVERDUE",
        })

    @staticmethod
    def normaliza_pagamento(item: dict, cust_map: dict = None) -> dict:
        cust_map = cust_map or {}
        return {
            "codigo":      item.get("id", ""),
            "descricao":   item.get("description") or "",
            "valor":       item.get("value", 0) or 0,
            "dtVenc":      item.get("dueDate", ""),
            "dtPgto":      item.get("paymentDate") or item.get("confirmedDate") or "",
            "nomeContato": cust_map.get(item.get("customer"), ""),
            "situacao":    item.get("status", ""),
            "metodo":      item.get("billingType", ""),
        }
