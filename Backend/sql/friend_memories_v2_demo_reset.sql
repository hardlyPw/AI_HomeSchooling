-- Demo reset support for AI_Friend / FriendView.
--
-- How to use:
-- 1. First make friend_memories_v2 contain the exact memories you want as the
--    demo baseline.
-- 2. Run the "capture baseline" block once.
-- 3. Run the function/policy block.
-- 4. The app reset button can call reset_friend_memories_v2_to_demo_seed()
--    and restore friend_memories_v2 to the captured baseline.

-- Capture or refresh the demo baseline from the current live table.
create table if not exists public.friend_memories_v2_demo_seed
(like public.friend_memories_v2 including all);

truncate table public.friend_memories_v2_demo_seed;

insert into public.friend_memories_v2_demo_seed (
  id,
  type,
  description,
  embedding_vector,
  poignancy,
  filling,
  emotion,
  created_at
)
select
  id,
  type,
  description,
  embedding_vector,
  poignancy,
  filling,
  emotion,
  created_at
from public.friend_memories_v2
order by id;

-- Reset live memory back to the captured baseline.
create or replace function public.reset_friend_memories_v2_to_demo_seed()
returns integer
language plpgsql
security definer
set search_path = public
as $$
declare
  restored_count integer;
  max_restored_id bigint;
begin
  truncate table public.friend_memories_v2 restart identity;

  insert into public.friend_memories_v2 (
    id,
    type,
    description,
    embedding_vector,
    poignancy,
    filling,
    emotion,
    created_at
  )
  select
    id,
    type,
    description,
    embedding_vector,
    poignancy,
    filling,
    emotion,
    created_at
  from public.friend_memories_v2_demo_seed
  order by id;

  select count(*), max(id)
    into restored_count, max_restored_id
  from public.friend_memories_v2;

  if max_restored_id is not null then
    perform setval(
      pg_get_serial_sequence('public.friend_memories_v2', 'id'),
      max_restored_id,
      true
    );
  end if;

  return restored_count;
end;
$$;

grant execute on function public.reset_friend_memories_v2_to_demo_seed()
to anon, authenticated;
