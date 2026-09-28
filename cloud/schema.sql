-- Run this once in the Supabase SQL editor.
-- Cloud uses a server-side Supabase secret key only.

create extension if not exists pgcrypto;

create table if not exists public.agents (
  agent_id text primary key,
  agent_version text not null default 'unknown',
  capabilities jsonb not null default '{}'::jsonb,
  status text not null default 'offline' check (status in ('online','offline')),
  last_seen timestamptz not null default now(),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.jobs (
  id uuid primary key default gen_random_uuid(),
  agent_id text not null references public.agents(agent_id) on delete cascade,
  status text not null default 'queued' check (status in ('queued','processing','completed','failed','cancelled')),
  payload jsonb not null,
  result jsonb,
  error text,
  idempotency_key text,
  attempts integer not null default 0,
  locked_at timestamptz,
  started_at timestamptz,
  completed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create unique index if not exists jobs_agent_idempotency_unique
  on public.jobs(agent_id, idempotency_key)
  where idempotency_key is not null;

create index if not exists jobs_claim_idx
  on public.jobs(agent_id, status, created_at);

alter table public.agents enable row level security;
alter table public.jobs enable row level security;

revoke all on public.agents from anon, authenticated;
revoke all on public.jobs from anon, authenticated;

create or replace function public.claim_next_job(
  p_agent_id text,
  p_lease_seconds integer default 900
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  v_job public.jobs;
begin
  update public.jobs
     set status = 'queued',
         locked_at = null,
         updated_at = now()
   where agent_id = p_agent_id
     and status = 'processing'
     and locked_at < now() - make_interval(secs => greatest(p_lease_seconds, 60));

  select *
    into v_job
    from public.jobs
   where agent_id = p_agent_id
     and status = 'queued'
   order by created_at
   for update skip locked
   limit 1;

  if not found then
    return null;
  end if;

  update public.jobs
     set status = 'processing',
         attempts = attempts + 1,
         locked_at = now(),
         started_at = coalesce(started_at, now()),
         updated_at = now()
   where id = v_job.id
  returning * into v_job;

  return jsonb_build_object(
    'job_id', v_job.id::text,
    'agent_id', v_job.agent_id,
    'status', v_job.status,
    'created_at', v_job.created_at,
    'attempts', v_job.attempts
  ) || v_job.payload;
end;
$$;

grant execute on function public.claim_next_job(text, integer) to service_role;
