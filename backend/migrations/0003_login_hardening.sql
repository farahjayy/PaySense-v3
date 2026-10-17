-- PaySense v3 — migration 0003: login and abuse hardening (ADR D-49, work package WP18).
-- Apply once, after 0002, in the Supabase SQL editor (see migrations/README.md).
--
--   * users.passphrase_hash: the second login factor, "scrypt$n$r$p$salt$hash" (never plain text).
--     A user without one cannot log in; set it with scripts/seed_users.py --passphrase-file.
--   * users.token_version: carried in every session token; logout increments it, so every older
--     token is refused (revocation).
--   * user_locks: one row per (user, lock name) while a plan is being created, so two server
--     processes cannot both create the same plan. The primary key makes taking a lock atomic.
--   * an index for the transaction list's keyset pagination (newest first by date, then id).
--
-- Same lock-down as every other table: RLS on, no policies, no anon/authenticated privileges.

begin;

alter table users add column passphrase_hash text
    check (passphrase_hash is null or passphrase_hash like 'scrypt$%');
alter table users add column token_version int not null default 0 check (token_version >= 0);

create table user_locks (
    user_id uuid not null references users(id) on delete cascade,
    name text not null check (name in ('plan_create')),
    acquired_at timestamptz not null default now(),
    primary key (user_id, name)
);
alter table user_locks enable row level security;
revoke all on user_locks from anon, authenticated;

create index transactions_user_date_id_idx on transactions (user_id, date desc, id desc);

commit;
