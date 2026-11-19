-- =============================================================================
-- 0004: deleting an account must actually work.
-- messages.user_id was ON DELETE SET NULL, but user messages must have an author
-- (check user_messages_have_author), so removing a profile failed. A person's messages only live in
-- their own conversations, which are deleted with them anyway: cascade.
-- =============================================================================
alter table messages drop constraint messages_user_id_fkey;
alter table messages add constraint messages_user_id_fkey
  foreign key (user_id) references profiles(id) on delete cascade;
