import os, sys
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
# Testes nunca tocam produção: sem Supabase (roteadores caem no SQLite local
# temporário) e baixa automática de créditos desligada.
os.environ.pop("SUPABASE_URL", None)
os.environ["CREDITOS_AUTO_BAIXA"] = "0"


class Resp:
    """Resposta HTTP simulada."""
    def __init__(self, status=200, body=b"", ctype="application/json", headers=None):
        self.status_code = status
        self.content = body if isinstance(body, bytes) else body.encode()
        self.text = self.content.decode("utf-8", "replace")
        self.headers = {"Content-Type": ctype, **(headers or {})}
        self.encoding = "utf-8"

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        import json
        return json.loads(self.text)
