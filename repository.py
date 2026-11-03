import uuid
from contextlib import contextmanager
from pathlib import Path
import psycopg
from psycopg.rows import dict_row
from app.models.domain import ApplicationInput, ReminderInput, Settings, NotFound

class Repository:
    def __init__(self, settings: Settings):
        self.settings = settings
    @contextmanager
    def connection(self):
        with psycopg.connect(self.settings.database_url, sslmode=self.settings.sslmode,
                             connect_timeout=3, row_factory=dict_row) as conn:
            yield conn
    def migrate(self):
        with self.connection() as c:
            c.execute("SELECT pg_advisory_xact_lock(7854321)")
            c.execute("CREATE TABLE IF NOT EXISTS schema_migrations (name TEXT PRIMARY KEY, applied_at TIMESTAMPTZ DEFAULT now())")
            for path in sorted((Path(__file__).parent / "migrations").glob("*.sql")):
                if not c.execute("SELECT 1 FROM schema_migrations WHERE name=%s", (path.name,)).fetchone():
                    c.execute(path.read_text())
                    c.execute("INSERT INTO schema_migrations(name) VALUES (%s)", (path.name,))
    def seed(self):
        with self.connection() as c:
            c.execute("SELECT pg_advisory_xact_lock(7854322)")
            if not c.execute("SELECT 1 FROM applications LIMIT 1").fetchone():
                c.execute("INSERT INTO applications(company,role,status,notes) VALUES (%s,%s,%s,%s)",
                          ("Example Studio", "Frontend Developer", "applied", "Demo record. Replace with your own application."))
    def ping(self):
        with self.connection() as c:
            c.execute("SELECT 1").fetchone()
    def list_applications(self):
        with self.connection() as c:
            return c.execute("SELECT * FROM applications ORDER BY created_at DESC, id DESC LIMIT 500").fetchall()
    def save(self, item: ApplicationInput, application_id=None):
        with self.connection() as c:
            values = (item.company, item.role, item.status, item.notes)
            if application_id is None:
                return c.execute("INSERT INTO applications(company,role,status,notes) VALUES (%s,%s,%s,%s) RETURNING *", values).fetchone()
            return c.execute("UPDATE applications SET company=%s,role=%s,status=%s,notes=%s,updated_at=now() WHERE id=%s RETURNING *", (*values, application_id)).fetchone()
    def delete(self, application_id):
        with self.connection() as c:
            return c.execute("DELETE FROM applications WHERE id=%s RETURNING id", (application_id,)).fetchone()
    def enqueue(self, application_id, reminder: ReminderInput):
        with self.connection() as c:
            app = c.execute("SELECT * FROM applications WHERE id=%s FOR KEY SHARE", (application_id,)).fetchone()
            if not app:
                return None
            return c.execute("""INSERT INTO email_jobs(id,application_id,recipient,subject,body,next_attempt_at)
              VALUES (%s,%s,%s,%s,%s,COALESCE(%s,now())) RETURNING *""",
              (uuid.uuid4(), application_id, reminder.recipient,
               f"Follow up: {app['role']} at {app['company']}",
               f"Reminder to follow up on your {app['role']} application at {app['company']}. Status: {app['status']}.",
               reminder.scheduled_at)).fetchone()
    def jobs(self):
        with self.connection() as c:
            return c.execute("SELECT * FROM email_jobs ORDER BY created_at DESC LIMIT 500").fetchall()
    def process_one(self, deliver):
        # Hold a row lock through delivery. On a crash the transaction rolls back;
        # a stable Resend idempotency key protects immediate re-delivery.
        with self.connection() as c:
            job = c.execute("""SELECT * FROM email_jobs WHERE status='pending' AND next_attempt_at<=now()
                ORDER BY next_attempt_at FOR UPDATE SKIP LOCKED LIMIT 1""").fetchone()
            if not job:
                return False
            attempts = job['attempts'] + 1
            try:
                provider_id = deliver(job)
            except Exception:
                # Never store provider exception strings: they may expose credentials.
                c.execute("""UPDATE email_jobs SET attempts=%s,status=%s,last_error=%s,
                    next_attempt_at=now() + %s * interval '1 second' WHERE id=%s""",
                    (attempts, 'failed' if attempts >= 4 else 'pending', 'Email provider delivery failed',
                     10 * 2 ** (attempts - 1), job['id']))
            else:
                c.execute("UPDATE email_jobs SET attempts=%s,status='sent',provider_id=%s,sent_at=now(),last_error=NULL WHERE id=%s",
                          (attempts, provider_id, job['id']))
            return True
