-- Custom application authentication; Supabase Auth is intentionally independent.
create table public.backchannel_users (
  id uuid primary key default gen_random_uuid(),
  email text not null unique check (email = lower(btrim(email))),
  password_hash text not null,
  created_at timestamptz not null default now()
);
create table public.backchannel_sessions (
  id uuid primary key,
  user_id uuid not null references public.backchannel_users(id) on delete cascade,
  expires_at timestamptz not null,
  revoked_at timestamptz,
  created_at timestamptz not null default now()
);
create index backchannel_sessions_user_idx on public.backchannel_sessions(user_id);
create index backchannel_sessions_expiry_idx on public.backchannel_sessions(expires_at);
create table public.backchannel_chats (
  id uuid primary key,
  user_id uuid not null references public.backchannel_users(id) on delete cascade,
  topic text not null,
  personas jsonb not null check (jsonb_typeof(personas) = 'array'),
  messages jsonb not null check (jsonb_typeof(messages) = 'array'),
  system_events jsonb not null check (jsonb_typeof(system_events) = 'array'),
  max_messages integer not null check (max_messages between 1 and 80),
  message_count integer not null check (message_count >= 0 and message_count <= max_messages),
  created_at timestamptz not null,
  ended_at timestamptz not null,
  reason text not null check (reason = 'max_reached')
);
create index backchannel_chats_owner_ended_idx
  on public.backchannel_chats(user_id, ended_at desc, id desc);
alter table public.backchannel_users enable row level security;
alter table public.backchannel_sessions enable row level security;
alter table public.backchannel_chats enable row level security;
revoke all on table public.backchannel_users, public.backchannel_sessions,
  public.backchannel_chats from public, anon, authenticated;
grant all on table public.backchannel_users, public.backchannel_sessions,
  public.backchannel_chats to service_role;
