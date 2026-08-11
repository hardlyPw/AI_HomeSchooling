-- Graph Match persistence for the single-user prototype.
-- Execute this file once in the Supabase SQL editor before enabling the game API.

create table if not exists public.graph_match_sessions (
    id text primary key,
    user_id text not null,
    agent_id text not null,
    agent_name text not null,
    agent_skill text not null check (agent_skill in ('easy', 'normal', 'hard')),
    current_round_index integer not null default 0 check (current_round_index between 0 and 2),
    user_total_score numeric(5, 1) not null default 0,
    agent_total_score numeric(5, 1) not null default 0,
    user_round_wins integer not null default 0,
    agent_round_wins integer not null default 0,
    completed boolean not null default false,
    activity_memories jsonb not null default '[]'::jsonb,
    created_at timestamptz not null,
    completed_at timestamptz
);

create table if not exists public.graph_match_rounds (
    session_id text not null references public.graph_match_sessions(id) on delete cascade,
    round_number integer not null check (round_number between 1 and 3),
    target_coefficient integer not null check (target_coefficient in (-1, 1)),
    target_base double precision not null,
    target_horizontal_shift integer not null,
    target_vertical_shift integer not null,
    user_coefficient integer,
    user_base double precision,
    user_horizontal_shift integer,
    user_vertical_shift integer,
    user_graph_score numeric(5, 1),
    user_time_bonus numeric(4, 1),
    user_score numeric(5, 1),
    user_elapsed_ms integer,
    agent_coefficient integer,
    agent_base double precision,
    agent_horizontal_shift integer,
    agent_vertical_shift integer,
    agent_graph_score numeric(5, 1),
    agent_time_bonus numeric(4, 1),
    agent_score numeric(5, 1),
    agent_elapsed_ms integer,
    winner text check (winner is null or winner in ('user', 'agent', 'draw')),
    completed boolean not null default false,
    primary key (session_id, round_number)
);

create table if not exists public.graph_match_quick_chats (
    id text primary key,
    session_id text not null references public.graph_match_sessions(id) on delete cascade,
    sender text not null check (sender in ('user', 'agent')),
    chat text not null check (chat in ('hello', 'nice', 'try_harder', 'great_play', 'close', 'good_game')),
    text text not null,
    created_at timestamptz not null
);

create index if not exists graph_match_sessions_user_created_idx
    on public.graph_match_sessions (user_id, created_at desc);

create index if not exists graph_match_quick_chats_session_created_idx
    on public.graph_match_quick_chats (session_id, created_at);
