-- Execute uma vez no SQL Editor do Supabase usado pelo Hub.
-- A aplicação acessa esta tabela somente pelo service role configurado nos Secrets.

create table if not exists public.hub_monitoring_state (
    id text primary key,
    payload jsonb not null default '{}'::jsonb,
    updated_at timestamptz not null default now()
);

alter table public.hub_monitoring_state enable row level security;

comment on table public.hub_monitoring_state is
    'Estado operacional, incidentes, contatos e auditoria da Central de Monitoramento do Hub.';
