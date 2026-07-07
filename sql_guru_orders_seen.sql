create table if not exists guru_orders_seen (
  guru_id text primary key,
  first_seen_at timestamptz default now()
);

alter table guru_orders_seen disable row level security;
