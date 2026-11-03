import hmac
import logging
from pathlib import Path
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from app.services.tracker import Tracker, ApplicationInput, ReminderInput, NotFound

router = APIRouter()
def service(request: Request) -> Tracker: return request.app.state.tracker
def authorize(request: Request, authorization: str = Header(default="")):
    token = request.app.state.tracker.settings.token
    if not hmac.compare_digest(authorization, f"Bearer {token}"):
        raise HTTPException(401, "Invalid API token")

@router.get("/", include_in_schema=False)
def dashboard(): return FileResponse(Path(__file__).with_name("dashboard.html"))
@router.get("/health")
def health(s: Tracker = Depends(service)):
    result = s.health()
    return JSONResponse(result, status_code=200 if result['database']=='up' else 503)

protected = APIRouter(prefix="/api", dependencies=[Depends(authorize)])
@protected.get("/applications")
def applications(s: Tracker = Depends(service)): return s.applications()
@protected.post("/applications", status_code=201)
def create(item: ApplicationInput, s: Tracker = Depends(service)): return s.save(item)
@protected.put("/applications/{application_id}")
def update(application_id: int, item: ApplicationInput, s: Tracker = Depends(service)): return s.save(item, application_id)
@protected.delete("/applications/{application_id}", status_code=204)
def delete(application_id: int, s: Tracker = Depends(service)):
    s.delete(application_id)
    return Response(status_code=204)
@protected.post("/applications/{application_id}/reminders", status_code=202)
def remind(application_id: int, item: ReminderInput, s: Tracker = Depends(service)): return s.remind(application_id, item)
@protected.get("/email-jobs")
def jobs(s: Tracker = Depends(service)): return s.jobs()
router.include_router(protected)

def install_errors(app):
    @app.exception_handler(NotFound)
    async def not_found(request, exc): return JSONResponse({"detail": str(exc)}, status_code=404)
    @app.exception_handler(Exception)
    async def unexpected(request, exc):
        logging.getLogger(__name__).error("request_failed")
        return JSONResponse({"detail": "Service temporarily unavailable"}, status_code=503)
