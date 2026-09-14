BEGIN;
CREATE TABLE IF NOT EXISTS media_job (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source_url text NOT NULL, platform varchar(32) NOT NULL,
  workflow varchar(32) NOT NULL, quality varchar(16) NOT NULL DEFAULT '1080',
  status varchar(32) NOT NULL DEFAULT 'queued', progress integer NOT NULL DEFAULT 0,
  title text, uploader varchar(255), duration_seconds integer, width integer, height integer,
  output_name text, delivery_url text, delivery_expires_at timestamptz,
  error_message text, worker_id varchar(128), claimed_at timestamptz, completed_at timestamptz,
  _created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
  _created_by user_profile,
  _updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
  _updated_by user_profile
);
CREATE TABLE IF NOT EXISTS media_worker_runtime (
  id varchar(128) PRIMARY KEY, version varchar(32) NOT NULL DEFAULT '0.1.0',
  last_seen timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
  _created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP, _created_by user_profile,
  _updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP, _updated_by user_profile
);
ALTER TABLE media_job ENABLE ROW LEVEL SECURITY;
ALTER TABLE media_worker_runtime ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename='media_job' AND policyname='lark_media_service') THEN
    CREATE POLICY lark_media_service ON media_job TO service_role USING (true) WITH CHECK (true);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename='media_job' AND policyname='lark_media_owner_app') THEN
    CREATE POLICY lark_media_owner_app ON media_job TO authenticated USING (true) WITH CHECK (true);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename='media_worker_runtime' AND policyname='lark_media_service') THEN
    CREATE POLICY lark_media_service ON media_worker_runtime TO service_role USING (true) WITH CHECK (true);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename='media_worker_runtime' AND policyname='lark_media_owner_app') THEN
    CREATE POLICY lark_media_owner_app ON media_worker_runtime TO authenticated USING (true) WITH CHECK (true);
  END IF;
END $$;
-- Miaoda's runtime roles are scoped to the app schema. The dev/online schema names differ.
-- Express the role condition dynamically so a published policy works in either environment.
ALTER POLICY lark_media_owner_app ON media_job TO PUBLIC
  USING (current_user = 'authenticated_' || current_schema())
  WITH CHECK (current_user = 'authenticated_' || current_schema());
ALTER POLICY lark_media_service ON media_job TO PUBLIC
  USING (current_user = 'service_role_' || current_schema())
  WITH CHECK (current_user = 'service_role_' || current_schema());
ALTER POLICY lark_media_owner_app ON media_worker_runtime TO PUBLIC
  USING (current_user = 'authenticated_' || current_schema())
  WITH CHECK (current_user = 'authenticated_' || current_schema());
ALTER POLICY lark_media_service ON media_worker_runtime TO PUBLIC
  USING (current_user = 'service_role_' || current_schema())
  WITH CHECK (current_user = 'service_role_' || current_schema());
CREATE INDEX IF NOT EXISTS idx_media_job_status_created ON media_job(status, _created_at);
CREATE INDEX IF NOT EXISTS idx_media_worker_runtime_last_seen ON media_worker_runtime(last_seen);
COMMIT;
