# Páginas arquivadas

Páginas movidas para fora de `pages/` para que não apareçam no menu lateral do
Streamlit, sem apagar o código. Para reativar uma página, mova o arquivo de
volta para `pages/` (`git mv archived_pages/NOME.py pages/NOME.py`).

## 11_Pagamentos.py
Removida do menu em 2026-09-03 a pedido da Michelle para revisão do módulo
("vamos dar uma limpada no sistema: retire pagamentos, precisamos rever ele").
O backend (`db_pagamentos.py`, `db_pagamentos_supabase.py`,
`db_pagamentos_sqlite.py`) e os dados no banco não foram alterados — só a
página de navegação saiu do ar.
