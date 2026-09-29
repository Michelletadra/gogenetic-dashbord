-- Baixa automática de créditos a partir do eGestor (2026-09-29)
-- Rodar UMA vez no Supabase SQL Editor. Pode rodar de novo sem problema
-- (tudo é "if not exists").

-- 1) Colunas de rastreabilidade na movimentação. As 3 primeiras normalmente
--    já existem em produção (usadas pelo "Usar crédito" manual desde set/2026);
--    "origem" é nova: 'auto_egestor' marca as baixas feitas pelo sistema.
alter table movimentacoes add column if not exists descricao_servico text;
alter table movimentacoes add column if not exists codigo_servico    text;
alter table movimentacoes add column if not exists servico_empresa   text;
alter table movimentacoes add column if not exists origem            text;

-- 2) Registro de cada pedido/OS do eGestor já processado pela baixa automática.
--    A chave (empresa, codigo) impede baixa em dobro, mesmo com a rotina de
--    hora em hora e alguém abrindo a tela ao mesmo tempo.
create table if not exists creditos_auto_log (
    empresa        text not null,
    codigo         text not null,
    status         text not null,          -- processando | baixado | pendente | ignorado
    cliente_id     bigint,
    nome_contato   text,
    valor          numeric,
    dt_venda       text,
    situacao       text,
    detalhe        text,
    atualizado_em  timestamptz default now(),
    primary key (empresa, codigo)
);

-- Mesmo padrão das demais tabelas do sistema (segurança feita no login do app).
alter table creditos_auto_log disable row level security;

-- Conferência: deve retornar relrowsecurity = false
select relname, relrowsecurity from pg_class where relname = 'creditos_auto_log';
