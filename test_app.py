import ast
import os
from pathlib import Path
from unittest.mock import Mock
import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.services.tracker import Tracker, Settings

TOKEN = 'test-only-token-at-least-24-characters'
def settings(url='postgresql://invalid:invalid@127.0.0.1:1/invalid'):
    return Settings(url, 'disable', TOKEN, '', 'test@example.com', False)

@pytest.fixture
def tracker(): return Tracker(settings())
@pytest.fixture
def client(tracker):
    with TestClient(create_app(tracker), raise_server_exceptions=False) as c:
        c.headers['Authorization'] = 'Bearer '+TOKEN
        yield c

def test_health_success(client, tracker):
    tracker.repo.ping = Mock()
    r=client.get('/health')
    assert r.status_code==200 and r.json()=={'app':'up','database':'up'}
def test_health_database_failure(client, tracker):
    tracker.repo.ping = Mock(side_effect=RuntimeError('private database password'))
    r=client.get('/health')
    assert r.status_code==503 and r.json()=={'app':'up','database':'down'}
def test_authentication(client):
    assert client.get('/api/applications', headers={'Authorization':''}).status_code==401
    assert client.get('/health', headers={'Authorization':''}).status_code==503

def test_validation(client):
    for body in [{'company':' ', 'role':'Engineer'}, {'company':'Example','role':'Engineer','status':'unknown'}]:
        assert client.post('/api/applications', json=body).status_code==422
    assert client.post('/api/applications/1/reminders',json={'recipient':'invalid'}).status_code==422
    assert client.post('/api/applications/1/reminders',json={'recipient':'me@example.com','scheduled_at':'2026-01-01T12:00:00'}).status_code==422

def test_reminder_only_enqueues(client, tracker):
    tracker.repo.enqueue=Mock(return_value={'id':'example','status':'pending'})
    tracker.deliver=Mock(side_effect=AssertionError('Endpoints must never send'))
    r=client.post('/api/applications/1/reminders', json={'recipient':'me@example.com'})
    assert r.status_code==202 and r.json()['status']=='pending'
    tracker.repo.enqueue.assert_called_once()
    tracker.deliver.assert_not_called()

def test_missing_application(client, tracker):
    tracker.repo.enqueue=Mock(return_value=None)
    assert client.post('/api/applications/999/reminders',json={'recipient':'me@example.com'}).status_code==404

def test_architecture():
    allowed={'api':'services','services':'data','data':'models'}
    for layer, below in allowed.items():
        for path in (Path('app')/layer).glob('*.py'):
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node,ast.ImportFrom) and (node.module or '').startswith('app.'):
                    assert node.module.split('.')[1] in (layer,below), str(path)
                if layer!='api' and isinstance(node,ast.ImportFrom):
                    assert not (node.module or '').startswith(('fastapi','starlette'))

def test_dashboard(client):
    r=client.get('/')
    assert r.status_code==200 and 'Application tracker' in r.text

@pytest.fixture
def database_tracker():
    url=os.getenv('TEST_DATABASE_URL')
    if not url: pytest.skip('Set TEST_DATABASE_URL to a dedicated PostgreSQL test database')
    t=Tracker(settings(url));t.migrate()
    with t.repo.connection() as c:
        c.execute('TRUNCATE email_jobs, applications RESTART IDENTITY CASCADE')
    yield t

def test_database_crud_and_retries(database_tracker):
    t=database_tracker
    with TestClient(create_app(t)) as c:
        c.headers['Authorization']='Bearer '+TOKEN
        r=c.post('/api/applications', json={'company':'Test Co','role':'Developer','status':'applied'})
        assert r.status_code==201
        aid=r.json()['id']
        assert len(c.get('/api/applications').json())==1
        assert c.put(f'/api/applications/{aid}',json={'company':'Test Co','role':'Developer','status':'interview'}).json()['status']=='interview'
        r=c.post(f'/api/applications/{aid}/reminders',json={'recipient':'me@example.com'})
        assert r.status_code==202
        job_id=r.json()['id']
        t.deliver=Mock(side_effect=RuntimeError('provider failure'))
        for attempt in range(1,5):
            assert t.process_one()
            job=t.jobs()[0]
            assert job['attempts']==attempt
            assert job['status']==('failed' if attempt==4 else 'pending')
            with t.repo.connection() as conn:
                conn.execute("UPDATE email_jobs SET next_attempt_at=now() WHERE id=%s",(job_id,))
        assert not t.process_one()
        assert t.deliver.call_count==4
        assert c.delete(f'/api/applications/{aid}').status_code==204
        assert t.jobs()==[]

def test_database_success_and_schedule(database_tracker):
    t=database_tracker
    from app.services.tracker import ApplicationInput, ReminderInput
    from datetime import datetime, timedelta, timezone
    a=t.save(ApplicationInput(company='Co',role='Dev'))
    t.remind(a['id'],ReminderInput(recipient='me@example.com',scheduled_at=datetime.now(timezone.utc)+timedelta(days=1)))
    t.deliver=Mock(return_value='provider-id')
    assert not t.process_one()
    t.remind(a['id'],ReminderInput(recipient='me@example.com'))
    assert t.process_one()
    sent=[j for j in t.jobs() if j['status']=='sent'][0]
    assert sent['attempts']==1 and sent['provider_id']=='provider-id' and sent['sent_at']
    t.deliver.assert_called_once()

def test_resend_payload_and_idempotency(tracker, monkeypatch):
    import httpx
    captured=[]
    def handler(request):
        import json
        captured.append((request.headers, json.loads(request.content)))
        return httpx.Response(200,json={'id':'provider-message-id'})
    original=httpx.Client
    transport=httpx.MockTransport(handler)
    monkeypatch.setattr('app.services.tracker.httpx.Client',lambda **kwargs:original(transport=transport,**kwargs))
    tracker.settings=Settings('', 'disable', TOKEN, 'test-key', 'sender@example.com', False)
    job={'id':'stable-id','recipient':'me@example.com','subject':'Follow up','body':'Reminder text'}
    assert tracker.deliver(job)=='provider-message-id'
    assert tracker.deliver(job)=='provider-message-id'
    assert captured[0][0]['idempotency-key']==captured[1][0]['idempotency-key']=='job-tracker/stable-id'
    assert captured[0][1]=={'from':'sender@example.com','to':['me@example.com'],'subject':'Follow up','text':'Reminder text'}

def test_worker_recovers_from_database_failure(tracker):
    import threading
    stop=threading.Event()
    calls=[]
    def process():
        calls.append(1)
        if len(calls)==1: raise RuntimeError('database unavailable')
        stop.set()
        return False
    tracker.process_one=process
    tracker.settings=Settings('', 'disable', TOKEN, '', '', True, .001)
    tracker.run_worker(stop)
    assert len(calls)==2
