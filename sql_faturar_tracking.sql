create table if not exists faturar_tracking (
  codigo bigint primary key,
  data_entrada date,
  cliente_nome text
);

alter table faturar_tracking disable row level security;

notify pgrst, 'reload schema';
