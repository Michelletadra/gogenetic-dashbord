-- Arquivo de dados históricos (vendas/faturamento/contas) de períodos já
-- fechados — anos anteriores ao ano corrente, que não mudam mais. Guardado
-- pra sempre, uma vez só, pra parar de bater na API do eGestor/Bling toda
-- vez que alguém abre uma página com comparação histórica. Rodar uma vez no
-- Supabase SQL Editor.
--
-- Se um período arquivado precisar ser recalculado (ex.: um lançamento
-- retroativo foi corrigido no eGestor/Bling depois do ano já ter fechado),
-- apague a(s) linha(s) correspondente(s) aqui — a próxima abertura da
-- página busca de novo na API e arquiva o valor atualizado.

create table if not exists dados_arquivados (
  empresa    text not null,
  chave      text not null,
  dados      jsonb not null,
  criado_em  timestamptz default now(),
  primary key (empresa, chave)
);

alter table dados_arquivados disable row level security;

notify pgrst, 'reload schema';
