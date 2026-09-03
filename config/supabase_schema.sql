-- ============================================================================
-- Genartml finance schema
-- Paste this whole file into Supabase -> SQL Editor -> Run.
-- ============================================================================

create extension if not exists "pgcrypto";

create table if not exists expenses (
  id             uuid primary key default gen_random_uuid(),
  spent_on       date not null,
  month_key      text not null,
  category       text not null,
  vendor         text,
  description    text,
  amount         numeric(12,2) not null check (amount >= 0),
  tax_amount     numeric(12,2) default 0,
  payment_method text,
  invoice_number text,
  status         text default 'paid',
  file_name      text,
  file_path      text,
  notes          text,
  created_at     timestamptz not null default now()
);
create index if not exists idx_expenses_month on expenses(month_key);
create index if not exists idx_expenses_cat   on expenses(category);

create table if not exists payroll_runs (
  id               uuid primary key default gen_random_uuid(),
  month_key        text not null unique,
  working_days     int  not null,
  headcount        int  not null,
  total_base       numeric(12,2) not null,
  total_ot         numeric(12,2) not null,
  total_allowance  numeric(12,2) not null,
  total_incentive  numeric(12,2) not null,
  total_gross      numeric(12,2) not null,
  total_tax        numeric(12,2) not null,
  total_net        numeric(12,2) not null,
  detail           jsonb not null,
  created_at       timestamptz not null default now()
);

-- Storage bucket for invoice files (private).
insert into storage.buckets (id, name, public)
values ('invoices', 'invoices', false)
on conflict (id) do nothing;

-- ============================================================================
-- SECURITY
--
-- RLS stays ON and no policy is granted to anon. That means a publishable
-- key CANNOT read or write these tables.
--
-- This app is a server running on your own machine — the browser talks to
-- your Flask app, never to Supabase directly. So the SECRET key belongs in
-- config/secrets.json, where no browser can see it, and it bypasses RLS.
--
-- Result: your salary and expense data is reachable only by someone holding
-- the secret key, not by anyone who happens to have the publishable one.
-- ============================================================================

alter table expenses     enable row level security;
alter table payroll_runs enable row level security;

-- If you ever DO need the publishable key to work (not recommended for
-- payroll data), uncomment these four lines instead:
-- create policy anon_all on expenses     for all to anon using (true) with check (true);
-- create policy anon_all on payroll_runs for all to anon using (true) with check (true);
-- create policy anon_files on storage.objects for all to anon
--   using (bucket_id = 'invoices') with check (bucket_id = 'invoices');
