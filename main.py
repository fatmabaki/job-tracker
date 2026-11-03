import logging
import os
import threading
from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.services.tracker import Tracker, Settings
from app.api.routes import router, install_errors

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s %(message)s')
def load_settings():
    token = os.environ.get("API_TOKEN", "")
    if len(token) < 24:
        raise RuntimeError("Set API_TOKEN to at least 24 characters")
    return Settings(database_url=os.environ["DATABASE_URL"], sslmode=os.getenv("DB_SSLMODE", "prefer"),
        token=token, resend_key=os.getenv("RESEND_API_KEY", ""),
        email_from=os.getenv("EMAIL_FROM", "Job Tracker <onboarding@resend.dev>"),
        worker_enabled=os.getenv("WORKER_ENABLED", "true").lower()=="true",
        poll_seconds=max(0.1, float(os.getenv("WORKER_POLL_SECONDS", "2"))))

def create_app(tracker=None):
    @asynccontextmanager
    async def lifespan(app):
        stop = threading.Event()
        worker = None
        if app.state.tracker.settings.worker_enabled:
            worker = threading.Thread(target=app.state.tracker.run_worker, args=(stop,), daemon=True)
            worker.start()
        yield
        stop.set()
        if worker: worker.join(timeout=20)
    app = FastAPI(title="JobFlow — Job Application Tracker", lifespan=lifespan)
    app.state.tracker = tracker or Tracker(load_settings())
    app.include_router(router)
    install_errors(app)
    return app
