"""Cliente da API do Digital Manager Guru (vendas/produtos da GoGenetic You)."""
import time
from datetime import datetime, timedelta

from http_seguro import ErroEsquema, exigir_lista, get_json

API = "https://digitalmanager.guru/api/v2"
MAX_DIAS_POR_JANELA = 180  # limite da própria API do Guru


class GuruClient:
    def __init__(self, token: str, _http_get=None, _dormir=time.sleep):
        self._token = token
        self._http_get = _http_get
        self._dormir = _dormir

    def _get(self, endpoint: str, params: dict = None) -> dict:
        return get_json(f"{API}/{endpoint}",
                        headers={"Authorization": f"Bearer {self._token}", "Accept": "application/json"},
                        params=params, provedor="Guru", empresa="GoGenetic You",
                        timeout=20, max_tentativas=3, http_get=self._http_get, dormir=self._dormir)

    def _transacoes_janela(self, dt_ini: str, dt_fim: str) -> list:
        """Busca todas as transações de uma janela (a API exige range <= 180 dias)."""
        result = []
        cursor = None
        for _ in range(1000):   # trava contra cursor que nunca termina
            params = {"ordered_at_ini": dt_ini, "ordered_at_end": dt_fim}
            if cursor:
                params["cursor"] = cursor
            data = self._get("transactions", params)
            result.extend(exigir_lista(data, "data", provedor="Guru", endpoint="transactions"))
            if not data.get("has_more_pages") or not data.get("next_cursor"):
                break
            cursor = data["next_cursor"]
        else:
            raise ErroEsquema("transactions: paginação não terminou após 1000 páginas", provedor="Guru")
        return result

    def get_transacoes(self, dt_ini: str, dt_fim: str) -> list:
        """Busca transações no período, quebrando em janelas <= 180 dias."""
        ini = datetime.strptime(dt_ini, "%Y-%m-%d")
        fim = datetime.strptime(dt_fim, "%Y-%m-%d")
        result = []
        janela_ini = ini
        while janela_ini <= fim:
            janela_fim = min(janela_ini + timedelta(days=MAX_DIAS_POR_JANELA - 1), fim)
            result.extend(self._transacoes_janela(
                janela_ini.strftime("%Y-%m-%d"), janela_fim.strftime("%Y-%m-%d")))
            janela_ini = janela_fim + timedelta(days=1)
        return result

    @staticmethod
    def normaliza_transacao(item: dict) -> dict:
        contact  = item.get("contact") or {}
        product  = item.get("product") or {}
        payment  = item.get("payment") or {}
        dates    = item.get("dates") or {}
        ordered_at = dates.get("ordered_at")
        dt_venda = (
            datetime.fromtimestamp(ordered_at).strftime("%Y-%m-%d")
            if ordered_at else ""
        )
        return {
            "codigo":      item.get("id", ""),
            "dtVenda":     dt_venda,
            "produto":     product.get("name", ""),
            "valorTotal":  payment.get("gross", 0) or 0,
            "nomeContato": contact.get("name", ""),
            "status":      item.get("status", ""),
            "metodo":      payment.get("method", ""),
        }
