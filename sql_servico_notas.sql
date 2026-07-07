create table if not exists servico_notas (
  codigo text primary key,
  nota text,
  updated_at timestamptz default now()
);

alter table servico_notas disable row level security;
