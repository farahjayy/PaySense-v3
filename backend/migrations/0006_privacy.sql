-- PaySense v3 — migration 0006: privacy notice acceptance (WP19).
-- Apply once, after 0005, in the Supabase SQL editor (see migrations/README.md).
--
-- The version of the privacy and assistant notice the person accepted, and when. The assistant
-- does not call the model provider until the current version is accepted (guided mode still
-- works). No new table: the rows live on user_settings, which already has RLS on and no
-- anon/authenticated privileges.

begin;

alter table user_settings add column consent_version text
    check (consent_version is null or length(consent_version) between 1 and 20);
alter table user_settings add column consent_at timestamptz;

commit;
