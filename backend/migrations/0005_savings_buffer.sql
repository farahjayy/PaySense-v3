-- PaySense v3 — migration 0005: the optional savings buffer (ADR D-50, work package WP16).
-- Apply once, after 0004, in the Supabase SQL editor (see migrations/README.md).
--
-- What the person could fall back on if a month runs short, in integer sen (0 = none recorded).
-- Engine 1's running margin starts from it and Engine 2 reads it as a feature. user_settings
-- already has RLS on with no policies and no anon/authenticated privileges (0001).

begin;

alter table user_settings add column savings_buffer_sen bigint not null default 0
    check (savings_buffer_sen >= 0);

commit;
