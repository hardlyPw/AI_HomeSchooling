# Database SQL

This directory contains database objects that cannot be represented safely as
ordinary application service code. Keep SQL functions, grants, seed helpers,
and schema migrations here so a new Supabase environment can be reproduced.

## Current scripts

`friend_memories_v2_demo_reset.sql` creates the
`reset_friend_memories_v2_to_demo_seed` RPC used by the Jiho debug reset flow.
It also owns the function security mode and execute grant, so it must remain a
database script rather than being embedded in Python.

Run the script in the Supabase SQL editor after the `friend_memories_v2` table
and demo seed rows exist. The application calls the RPC by the name configured
in the Agent runtime definition.

`graph_match_games.sql` creates the session, round, and quick-chat tables used
by `SupabaseGraphMatchRepository`. Run it once before starting Graph Match with
Supabase. These tables currently hold backend-owned single-user prototype data;
authentication and row-level ownership policies remain a later task.

Graph Match uses Supabase by default. Set `GRAPH_MATCH_STORAGE=memory` only for
local-only runs. If Supabase is temporarily unavailable, the resilient
repository keeps the current process playable and retries remote persistence
after a cooldown.

## Growth rule

Keep SQL files flat in this directory while the set is small. Split them into
`migrations/`, `functions/`, and `seeds/` only when at least one of these is
true:

- deployment order must be tracked across multiple schema changes;
- three or more scripts have different migration, function, or seed roles;
- a migration tool is introduced and requires numbered files.

Do not replace schema or RPC scripts with startup-time application code. That
would hide deployment state and make permission changes difficult to audit.
