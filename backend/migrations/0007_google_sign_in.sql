-- PaySense v3 — migration 0007: Sign in with Google (ADR D-69).
-- Apply once, after 0006, in the Supabase SQL editor (see migrations/README.md).
--
--   * users.google_sub: Google's stable account id; a Google user is found by it, never by email.
--     NULL for passphrase accounts (a NULL never collides in a unique index).
--   * users.email: the verified email Google reported at the last sign-in.
--   * auth_events: sign-up, login, failed login and logout. Insert-only. A failed login has no
--     user. Cascades from users, so "delete my account" removes a person's history (WP19).
--     RLS on with no policies and no anon/authenticated privileges, like every other table.

begin;

alter table users add column google_sub text check (google_sub is null or length(google_sub) between 1 and 255);
alter table users add column email text check (email is null or length(email) between 3 and 320);
create unique index users_google_sub_key on users (google_sub);

create table auth_events (
    id uuid primary key default gen_random_uuid(),
    event text not null check (event in ('signup', 'login', 'login_failed', 'logout')),
    user_id uuid references users(id) on delete cascade,
    email text check (email is null or length(email) <= 320),
    reason text check (
        (event = 'login_failed') = (reason is not null)
        and (reason is null or reason in ('cancelled', 'state', 'exchange', 'token'))
    ),
    ip text check (ip is null or length(ip) <= 64),
    user_agent text check (user_agent is null or length(user_agent) <= 500),
    created_at timestamptz not null default now()
);
create index auth_events_user on auth_events (user_id, created_at desc);
create index auth_events_created_at on auth_events (created_at desc);

alter table auth_events enable row level security;
revoke all on auth_events from anon, authenticated;

commit;
