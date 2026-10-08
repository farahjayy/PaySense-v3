-- PaySense v2 — migration 0001: initial schema.
-- Apply once, in the Supabase SQL editor, on a fresh project (see migrations/README.md).
--
-- Rules this file enforces (CLAUDE.md hard constraints 4 and 7, ADR D-03, D-16, D-26):
--   * every table except `users` has `user_id` and every cross-table link is a COMPOSITE
--     (id, user_id) foreign key, so a row can never point at another user's row;
--   * money is stored as integer sen (bigint), never numeric/float;
--   * row level security is ON for every table with NO policies, and anon/authenticated
--     privileges are revoked — only the backend (service key) can read or write.

begin;

-- ---------------------------------------------------------------- users
create table users (
    id uuid primary key default gen_random_uuid(),
    -- Same rule as app/db/users.py USERNAME_PATTERN, so a hand-inserted user can always log in.
    username text not null check (username ~ '^[A-Za-z0-9_.-]{1,64}$'),
    display_name text not null check (length(btrim(display_name)) > 0),
    persona text check (persona in ('frequent_bnpl', 'budget_conscious', 'irregular_income')),
    created_at timestamptz not null default now()
);
create unique index users_username_lower_key on users (lower(username));

-- D-27: there is deliberately NO balance column. Students rarely keep a reliable account
-- balance, so forecasting runs on income and expense flows, not on a starting balance.
create table user_settings (
    user_id uuid primary key references users(id) on delete cascade,
    onboarding_state text not null default 'new'
        check (onboarding_state in ('new', 'history_imported', 'complete'))
);

-- ---------------------------------------------------------------- recurring items
create table recurring_items (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references users(id) on delete cascade,
    kind text not null check (kind in ('income', 'bill')),
    name text not null check (length(btrim(name)) > 0),
    amount_sen bigint not null check (amount_sen > 0),
    cadence text not null check (cadence in ('weekly', 'biweekly', 'monthly', 'semester', 'custom')),
    custom_interval_days int check (custom_interval_days > 0),
    anchor_date date not null,
    active boolean not null default true,
    origin text not null check (origin in ('detected', 'manual')),
    created_at timestamptz not null default now(),
    unique (id, user_id),
    check (cadence <> 'custom' or custom_interval_days is not null)
);
create index recurring_items_user_idx on recurring_items (user_id, active);

-- ---------------------------------------------------------------- risk checks (frozen reports)
create table risk_checks (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references users(id) on delete cascade,
    input jsonb not null,
    features jsonb not null,
    feature_schema_hash text not null,
    model_version text not null,
    p numeric(7,6) not null check (p between 0 and 1),
    p_simulated numeric(7,6) not null check (p_simulated between 0 and 1),
    score int not null check (score between 0 and 100),
    label text not null check (label in ('safe', 'caution', 'at_risk')),
    factors jsonb not null,
    counterfactuals jsonb,
    repayment_flag jsonb,
    curves jsonb,
    created_at timestamptz not null default now(),
    unique (id, user_id)
);
create index risk_checks_user_idx on risk_checks (user_id, created_at desc);

-- ---------------------------------------------------------------- BNPL plans
create table bnpl_plans (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references users(id) on delete cascade,
    item_name text not null check (length(btrim(item_name)) > 0),
    -- D-24: three rule-driven providers; everything else is 'other' with a typed label.
    provider text not null check (provider in ('spaylater', 'tiktok_paylater', 'atome', 'other')),
    provider_label text not null check (length(btrim(provider_label)) > 0),
    schedule_source text not null default 'provider_rule'
        check (schedule_source in ('provider_rule', 'manual')),
    total_price_sen bigint not null check (total_price_sen > 0),
    monthly_fee_rate_pct numeric(5,2) not null default 0 check (monthly_fee_rate_pct >= 0),
    num_installments int not null check (num_installments between 1 and 36),
    first_payment_date date not null,
    status text not null default 'active' check (status in ('active', 'completed', 'overdue')),
    risk_score_at_creation int check (risk_score_at_creation between 0 and 100),
    risk_check_id uuid,
    risk_check_type text check (risk_check_type in ('before_purchase', 'current_state')),
    created_at timestamptz not null default now(),
    unique (id, user_id),
    foreign key (risk_check_id, user_id) references risk_checks (id, user_id)
        on delete set null (risk_check_id)
);
create index bnpl_plans_user_idx on bnpl_plans (user_id, status);
create index bnpl_plans_risk_check_idx on bnpl_plans (risk_check_id);

create table bnpl_installments (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references users(id) on delete cascade,
    plan_id uuid not null,
    seq int not null check (seq >= 1),
    due_date date not null,
    amount_sen bigint not null check (amount_sen > 0),
    is_paid boolean not null default false,
    paid_date date,
    unique (plan_id, seq),
    foreign key (plan_id, user_id) references bnpl_plans (id, user_id) on delete cascade,
    check (is_paid or paid_date is null)
);
create index bnpl_installments_user_due_idx on bnpl_installments (user_id, due_date);

-- ---------------------------------------------------------------- transactions
create table transactions (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references users(id) on delete cascade,
    date date not null,
    amount_sen bigint not null check (amount_sen > 0),
    type text not null check (type in ('income', 'expense', 'savings')),
    category text not null,
    description text,
    account_name text,
    is_bnpl boolean not null default false,
    source text not null default 'manual' check (source in ('manual', 'csv', 'seed')),
    bnpl_plan_id uuid,
    recurring_item_id uuid,
    created_at timestamptz not null default now(),
    foreign key (bnpl_plan_id, user_id) references bnpl_plans (id, user_id)
        on delete set null (bnpl_plan_id),
    foreign key (recurring_item_id, user_id) references recurring_items (id, user_id)
        on delete set null (recurring_item_id)
);
create index transactions_user_date_idx on transactions (user_id, date desc);
create index transactions_user_type_idx on transactions (user_id, type);
create index transactions_plan_idx on transactions (bnpl_plan_id);
create index transactions_recurring_idx on transactions (recurring_item_id);

-- ---------------------------------------------------------------- provider limits
create table provider_limits (
    user_id uuid not null references users(id) on delete cascade,
    provider text not null check (provider in ('spaylater', 'tiktok_paylater', 'atome', 'other')),
    limit_sen bigint not null check (limit_sen > 0),
    updated_at timestamptz not null default now(),
    primary key (user_id, provider)
);

-- ---------------------------------------------------------------- lock the tables down
alter table users enable row level security;
alter table user_settings enable row level security;
alter table recurring_items enable row level security;
alter table risk_checks enable row level security;
alter table bnpl_plans enable row level security;
alter table bnpl_installments enable row level security;
alter table transactions enable row level security;
alter table provider_limits enable row level security;

-- No policies are created on purpose. As defence in depth, also drop the default grants...
revoke all on users, user_settings, recurring_items, risk_checks, bnpl_plans,
    bnpl_installments, transactions, provider_limits from anon, authenticated;

-- ...and stop Supabase's default privileges from re-granting them on tables, sequences and
-- functions created by FUTURE migrations (a later table that forgets RLS must not be public).
alter default privileges in schema public revoke all on tables from anon, authenticated;
alter default privileges in schema public revoke all on sequences from anon, authenticated;
alter default privileges in schema public revoke all on functions from anon, authenticated;

commit;
