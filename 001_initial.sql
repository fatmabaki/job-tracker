CREATE TABLE applications (
 id BIGSERIAL PRIMARY KEY,
 company VARCHAR(150) NOT NULL,
 role VARCHAR(150) NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('saved','applied','interview','offer','rejected')),
 notes TEXT NOT NULL DEFAULT '',
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE email_jobs (
 id UUID PRIMARY KEY,
 application_id BIGINT NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
 recipient VARCHAR(254) NOT NULL,
 subject TEXT NOT NULL,
 body TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','sent','failed')),
 attempts INTEGER NOT NULL DEFAULT 0 CHECK(attempts BETWEEN 0 AND 4),
 next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 provider_id TEXT,
 last_error TEXT,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 sent_at TIMESTAMPTZ
);
CREATE INDEX email_jobs_due ON email_jobs(next_attempt_at) WHERE status='pending';
