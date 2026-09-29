-- Enable UUID extension
create extension if not exists "uuid-ossp";

-- 1. Configs Table (Replaces local JSON files)
create table if not exists public.configs (
    key text primary key,
    value jsonb default '{}'::jsonb,
    updated_at timestamp with time zone default timezone('utc'::text, now())
);

-- 2. Expenses Table (From finance.py)
create table if not exists public.expenses (
    id uuid primary key default uuid_generate_v4(),
    spent_on date not null,
    month_key text not null,
    category text not null,
    vendor text,
    description text,
    amount numeric not null,
    tax_amount numeric default 0,
    payment_method text,
    invoice_number text,
    status text default 'paid',
    file_name text,
    file_path text,
    notes text,
    created_at timestamp with time zone default timezone('utc'::text, now())
);

-- 3. Payroll Runs Table (From finance.py)
create table if not exists public.payroll_runs (
    month_key text primary key,
    run_date date not null,
    total_net numeric not null,
    headcount integer not null,
    detail jsonb default '[]'::jsonb,
    created_at timestamp with time zone default timezone('utc'::text, now())
);

-- Enable RLS and create open policy for backend service role
alter table public.configs enable row level security;
create policy "Service Role Full Access" on public.configs for all using (true);

alter table public.expenses enable row level security;
create policy "Service Role Full Access" on public.expenses for all using (true);

alter table public.payroll_runs enable row level security;
create policy "Service Role Full Access" on public.payroll_runs for all using (true);


-- 4. Storage Buckets for Timesheets and Payslips
insert into storage.buckets (id, name, public) 
values 
  ('timesheets', 'timesheets', true),
  ('payslips', 'payslips', true)
on conflict (id) do nothing;
