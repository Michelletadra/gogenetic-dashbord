# App de Créditos — Grupo GoGenetic

Sistema independente, só com a gestão de créditos de clientes, para ser usado
por colaboradores sem acesso ao dashboard financeiro. Usa o mesmo banco
(Supabase) e a mesma tela do dashboard (`creditos_body.py`): tudo que for
lançado aqui aparece no dashboard, e vice-versa.

## Publicar (Streamlit Community Cloud)

1. share.streamlit.io → **Create app** → repositório `Michelletadra/gogenetic-dashbord`,
   branch `main`, **Main file path: `creditos_app/app.py`**.
2. Em **Advanced settings → Secrets**, cole o bloco abaixo (copie os valores
   de SUPABASE e dos tokens do eGestor dos Secrets do dashboard atual).
   **Os blocos `[creditos_usuarios.*]` têm que ficar no FINAL** — no formato
   TOML tudo que vem depois de um cabeçalho `[...]` fica "dentro" dele.

```toml
SUPABASE_URL = "..."
SUPABASE_KEY = "..."
GOGENETIC_PESQUISA_TOKEN = "..."
GOGENETIC_SOLUCOES_TOKEN = "..."
GOSOLOS_TOKEN = "..."
CREDITOS_COOKIE_KEY = "troque-por-uma-frase-longa-qualquer"
# Opcional: nome da situação no eGestor que dispara a baixa (padrão abaixo)
CREDITO_SITUACAO_GATILHO = "Consumo de crédito"

[creditos_usuarios.colaborador]
name = "Nome do colaborador"
email = "colaborador@gogenetic.com.br"
password = "senha-inicial"

[creditos_usuarios.michelle]
name = "Michelle Tadra"
email = "michelle@gogenetic.com.br"
password = "sua-senha"
```

O nome entre `[creditos_usuarios.` e `]` é o usuário do login. Para tirar o
acesso de alguém, apague o bloco dele e salve os Secrets.

## Baixa automática pelo eGestor

Serviço (OS) com a situação **Consumo de crédito** no eGestor → baixa do valor
total do pedido no crédito do cliente que vence primeiro (FIFO). Regras
completas em `creditos_sync.py`. Roda:

- de hora em hora, sozinho (GitHub Actions, `.github/workflows/sync_creditos.yml`);
- ao abrir a tela de Créditos (no máximo a cada 10 min, últimos 60 dias);
- no botão **🤖 Sincronizar eGestor** (últimos 365 dias).

Serviços que o sistema não consegue decidir sozinho (cliente não encontrado,
nome ambíguo, sem crédito válido) ficam na aba **🤖 Baixas automáticas**.
