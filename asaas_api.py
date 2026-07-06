"""Cliente da API do Asaas (cobranças/pagamentos da GoGenetic You)."""
import time
from datetime import date, timedelta

import requests

API = "https://api.asaas.com/v3"

STATUS_RECEBIDO = ("RECEIVED", "CONFIRMED", "RECEIVED_IN_CASH")
STATUS_PENDENTE = ("PENDING", "AWAITING_RISK_ANALYSIS")


class AsaasClient:
    def __init__(self, api_key: str):
        self._key = api_key

    def _get(self, endpoint: str, params: dict = None) -> dict:
        resp = requests.get(
            f"{API}/{endpoint}",
            headers={"access_token": self._key, "User-Agent": "GoGeneticDashboard",
                      "Content-Type": "application/json"},
            params=params,
            timeout=20,
        )
        if resp.status_code == 429:
            time.sleep(5)
            return self._get(endpoint, params)
        resp.raise_for_status()
        return resp.json()

    def _pages(self, endpoint: str, params: dict = None) -> list:
        params = dict(params or {})
        result = []
        offset = 0
        limit = 100
        while True:
            params.update({"offset": offset, "limit": limit})
            data = self._get(endpoint, params)
            batch = data.get("data", [])
            result.extend(batch)
            if not data.get("hasMore"):
                break
            offset += limit
        return result

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
