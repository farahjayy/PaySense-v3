-- PaySense v3 — migration 0004: category budgets (WP2) and the assistant's tables (WP4b).
-- Apply once, after 0003, in the Supabase SQL editor (see migrations/README.md).
--
-- Same rules as every other table: user_id on every row, composite (id, user_id) keys so a row
-- can never point at another user's, money as bigint sen, RLS on with no policies and no
-- anon/authenticated privileges. Only the backend (service key) reads or writes.

begin;

-- ---------------------------------------------------------------- budgets (WP2)
create table budgets (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references users(id) on delete cascade,
    category text not null check (length(btrim(category)) between 1 and 60),
    limit_sen bigint not null check (limit_sen > 0),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (id, user_id)
);
-- "Food" and "food" are one budget for one person (ADR D-43).
create unique index budgets_user_category_key on budgets (user_id, lower(category));
alter table budgets enable row level security;
revoke all on budgets from anon, authenticated;

commit;
