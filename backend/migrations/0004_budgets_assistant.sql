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

-- ---------------------------------------------------------------- assistant (WP4b, ADR D-48)
-- A write the assistant proposed, waiting for the person to press Confirm. Single use: the
-- confirm endpoint claims it with an atomic status change; it expires after a few minutes.
create table assistant_actions (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references users(id) on delete cascade,
    type text not null check (type in ('add_transaction', 'confirm_import', 'create_plan',
                                        'set_budget', 'delete_budget')),
    payload jsonb not null,
    payload_digest text not null check (length(payload_digest) = 64),
    summary text not null check (length(summary) between 1 and 500),
    preview jsonb,
    status text not null default 'pending'
        check (status in ('pending', 'confirmed', 'declined', 'expired', 'failed')),
    result jsonb,
    created_at timestamptz not null default now(),
    expires_at timestamptz not null,
    decided_at timestamptz,
    unique (id, user_id)
);
create index assistant_actions_user_idx on assistant_actions (user_id, status, created_at desc);
alter table assistant_actions enable row level security;
revoke all on assistant_actions from anon, authenticated;

-- The audit log: every message, tool call, proposal, confirmation, refusal and fallback.
create table assistant_events (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references users(id) on delete cascade,
    kind text not null check (kind in ('message', 'reply', 'tool_call', 'proposal', 'confirm',
                                        'decline', 'refusal', 'fallback', 'error')),
    tier int check (tier between 0 and 2),
    tool text,
    status text,
    action_id uuid,
    provider text,
    model text,
    input_tokens int check (input_tokens >= 0),
    output_tokens int check (output_tokens >= 0),
    detail jsonb,
    created_at timestamptz not null default now(),
    foreign key (action_id, user_id) references assistant_actions (id, user_id)
        on delete set null (action_id)
);
create index assistant_events_user_idx on assistant_events (user_id, created_at desc);
alter table assistant_events enable row level security;
revoke all on assistant_events from anon, authenticated;

commit;
