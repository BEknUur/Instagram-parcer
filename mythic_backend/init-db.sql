-- file: init-db.sql  (копируй полностью)

-- создать базу, если ещё нет
SELECT 'CREATE DATABASE mythic'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'mythic');
\gexec                -- ← ОБЯЗАТЕЛЬНО с новой строки!

\c mythic

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'mythic') THEN
    CREATE USER mythic WITH PASSWORD 'mythic_password_2024';
  END IF;
END$$;

GRANT ALL PRIVILEGES ON DATABASE mythic TO mythic;
GRANT ALL PRIVILEGES ON SCHEMA public TO mythic;

------------------------------------------------------------------
-- users
------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
  id            uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  clerk_user_id varchar(255) UNIQUE NOT NULL,
  email         varchar(255),
  full_name     varchar(255),
  created_at    timestamptz DEFAULT CURRENT_TIMESTAMP,
  updated_at    timestamptz
);

------------------------------------------------------------------
-- processing_sessions
------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS processing_sessions (
  id                  uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  run_id              varchar(255) UNIQUE NOT NULL,
  user_id             uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  instagram_url       text NOT NULL,

  status              varchar(50)  DEFAULT 'started',
  current_stage       varchar(255),
  progress_percentage integer      DEFAULT 0,
  error_message       text,

  started_at          timestamptz  DEFAULT CURRENT_TIMESTAMP,
  completed_at        timestamptz
);

------------------------------------------------------------------
-- books
------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS books (
  id                  uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id             uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  run_id              varchar(255) NOT NULL,
  title               varchar(500) NOT NULL,

  profile_username    varchar(255),
  profile_full_name   varchar(255),
  profile_followers   integer,
  profile_posts_count integer,

  html_path           text,
  pdf_path            text,
  images_path         text,

  is_completed        boolean DEFAULT false,
  has_html            boolean DEFAULT false,
  has_pdf             boolean DEFAULT false,

  created_at          timestamptz DEFAULT CURRENT_TIMESTAMP,
  updated_at          timestamptz,
  book_metadata       text
);

------------------------------------------------------------------
-- индексы
------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_users_clerk        ON users(clerk_user_id);
CREATE INDEX IF NOT EXISTS idx_proc_run_id        ON processing_sessions(run_id);
CREATE INDEX IF NOT EXISTS idx_proc_user          ON processing_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_books_user         ON books(user_id);
CREATE INDEX IF NOT EXISTS idx_books_run_id       ON books(run_id);
CREATE INDEX IF NOT EXISTS idx_books_created_at   ON books(created_at);

------------------------------------------------------------------
-- auto-updated_at триггеры
------------------------------------------------------------------
CREATE OR REPLACE FUNCTION trg_set_updated_at()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  NEW.updated_at = CURRENT_TIMESTAMP;
  RETURN NEW;
END$$;

CREATE TRIGGER trg_users_upd
  BEFORE UPDATE ON users
  FOR EACH ROW EXECUTE FUNCTION trg_set_updated_at();

CREATE TRIGGER trg_books_upd
  BEFORE UPDATE ON books
  FOR EACH ROW EXECUTE FUNCTION trg_set_updated_at();

------------------------------------------------------------------
-- системный пользователь
------------------------------------------------------------------
INSERT INTO users (clerk_user_id, email, full_name)
VALUES ('system', 'system@mythic.app', 'System User')
ON CONFLICT (clerk_user_id) DO NOTHING;

DO $$
BEGIN
  RAISE NOTICE 'Mythic DB schema initialised successfully!';
END$$;
