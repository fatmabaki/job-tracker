import logging
import httpx
from app.data.repository import Repository, ApplicationInput, ReminderInput, Settings, NotFound

log = logging.getLogger(__name__)
class Tracker:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.repo = Repository(settings)
    def migrate(self): self.repo.migrate()
    def seed(self): self.repo.seed()
    def applications(self): return self.repo.list_applications()
    def save(self, item: ApplicationInput, application_id=None):
        result = self.repo.save(item, application_id)
        if not result: raise NotFound("Application not found")
        return result
    def delete(self, application_id):
        if not self.repo.delete(application_id): raise NotFound("Application not found")
    def remind(self, application_id, reminder: ReminderInput):
        result = self.repo.enqueue(application_id, reminder)
        if not result: raise NotFound("Application not found")
        return result
    def jobs(self): return self.repo.jobs()
    def health(self):
        try:
            self.repo.ping()
            return {"app": "up", "database": "up"}
        except Exception:
            return {"app": "up", "database": "down"}
    def deliver(self, job):
        if not self.settings.resend_key:
            raise RuntimeError("Email provider is not configured")
        with httpx.Client(timeout=15) as client:
            response = client.post("https://api.resend.com/emails", headers={
                "Authorization": f"Bearer {self.settings.resend_key}",
                "Idempotency-Key": f"job-tracker/{job['id']}"}, json={
                "from": self.settings.email_from, "to": [job['recipient']],
                "subject": job['subject'], "text": job['body']})
            response.raise_for_status()
            return response.json()["id"]
    def process_one(self): return self.repo.process_one(self.deliver)
    def run_worker(self, stop):
        while not stop.is_set():
            try:
                if self.process_one(): continue
            except Exception:
                log.error("worker_database_error")
            stop.wait(self.settings.poll_seconds)
