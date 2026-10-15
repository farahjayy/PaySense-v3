-- PaySense v2 — migration 0002: the categories a person adds themselves (ADR D-43).
-- Apply once, after 0001, in the Supabase SQL editor (see migrations/README.md).
--
-- The twelve built-in categories live in code (app/domain/categories.py) and are not stored.
-- This table holds only the person's own, so a category can exist before any transaction uses it.
-- A category typed in an imported spreadsheet needs no row: it exists on its transactions.
--
-- Same lock-down as every other table: row level security ON with NO policies, and no
-- anon/authenticated privileges. Only the backend (service key) reads or writes.

begin;

create table user_categories (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references users(id) on delete cascade,
    name text not null check (length(btrim(name)) between 1 and 40),
    created_at timestamptz not null default now()
);
-- "Gym" and "gym" are the same category for one person.
create unique index user_categories_user_name_key on user_categories (user_id, lower(name));

alter table user_categories enable row level security;
revoke all on user_categories from anon, authenticated;

commit;
