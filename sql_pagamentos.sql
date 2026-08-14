-- Gestão de Pagamentos — contas bancárias, saldos manuais, decisão de pagamentos
-- e histórico/auditoria. Rodar uma vez no Supabase SQL Editor.

create table if not exists contas_bancarias (
  id             bigint generated always as identity primary key,
  nome           text not null,
  banco          text,
  saldo_minimo   numeric default 0,
  limite_credito numeric default 0,
  ativo          boolean default true,
  criado_em      timestamptz default now()
);
alter table contas_bancarias add column if not exists limite_credito numeric default 0;

-- Histórico de saldos — nunca sobrescrever, sempre inserir novo registro.
create table if not exists saldos_bancarios (
  id               bigint generated always as identity primary key,
  conta_id         bigint references contas_bancarias(id) on delete cascade,
  valor            numeric not null default 0,
  saldo_reservado  numeric not null default 0,
  data_referencia  date not null,
  observacao       text,
  usuario          text,
  criado_em        timestamptz default now()
);
create index if not exists idx_saldos_bancarios_conta on saldos_bancarios(conta_id, data_referencia desc, criado_em desc);

-- Estado de decisão por pagamento (chave = empresa + código do título no eGestor/Bling).
create table if not exists pagamentos_overrides (
  id                bigint generated always as identity primary key,
  empresa           text not null,
  codigo            text not null,
  selecionado       boolean default false,
  conta_origem_id   bigint references contas_bancarias(id) on delete set null,
  centro_custo      text,
  projeto           text,
  valor_juros       numeric default 0,
  valor_desconto    numeric default 0,
  prioridade_manual text,
  status            text default 'Pendente de análise',
  observacao        text,
  valor_aprovado    numeric,
  atualizado_em     timestamptz default now(),
  atualizado_por    text,
  unique (empresa, codigo)
);

-- Auditoria: quem selecionou/aprovou/adiou/alterou e quando.
create table if not exists pagamentos_historico (
  id            bigint generated always as identity primary key,
  empresa       text not null,
  codigo        text not null,
  acao          text not null,
  valor_anterior text,
  valor_novo    text,
  usuario       text,
  criado_em     timestamptz default now()
);
create index if not exists idx_pagamentos_historico_titulo on pagamentos_historico(empresa, codigo, criado_em desc);

-- Snapshot de cada rodada de pagamento aprovada (relatório).
create table if not exists rodadas_pagamento (
  id              bigint generated always as identity primary key,
  criado_em       timestamptz default now(),
  usuario         text,
  total_titulos   int default 0,
  valor_bruto     numeric default 0,
  valor_juros     numeric default 0,
  valor_desconto  numeric default 0,
  valor_liquido   numeric default 0,
  saldos_antes    jsonb,
  pagamentos      jsonb,
  alertas         jsonb,
  observacao      text
);

alter table contas_bancarias    disable row level security;
alter table saldos_bancarios    disable row level security;
alter table pagamentos_overrides disable row level security;
alter table pagamentos_historico disable row level security;
alter table rodadas_pagamento   disable row level security;

notify pgrst, 'reload schema';
