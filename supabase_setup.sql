-- NUUK BIST Radar — Supabase Auth kurulumu
-- Çözme anahtarını (MASTER_KEY) yalnızca GİRİŞ YAPMIŞ + e-posta doğrulamış
-- kullanıcıya veren RLS korumalı tablo. Anon (giriş yapmamış) erişemez.

create table if not exists public.app_secrets (
  id    text primary key,
  value text not null
);

alter table public.app_secrets enable row level security;

-- Yalnızca authenticated rol (geçerli oturumu olan = e-posta doğrulanmış) okuyabilir.
drop policy if exists "authenticated okur" on public.app_secrets;
create policy "authenticated okur"
  on public.app_secrets for select
  to authenticated
  using (true);

-- MASTER_KEY buraya yazılır (base64). __MASTER_KEY__ derleme sırasında/elle doldurulur.
insert into public.app_secrets (id, value)
values ('master', '__MASTER_KEY__')
on conflict (id) do update set value = excluded.value;
