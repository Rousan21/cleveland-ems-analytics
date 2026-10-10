"""Local dashboard runner: starts immediately and refreshes stale data in background.

Not a public deployment. Closing its Terminal window ends the local server.
"""
import os
import subprocess
import sys
import time
import urllib.request
import webbrowser
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select
from db import SessionLocal, SyncRun, init_database

HERE = Path(__file__).resolve().parent


def due_for_refresh(now=None):
    now = now or datetime.now(timezone.utc)
    with SessionLocal() as db:
        latest = db.scalar(select(SyncRun).order_by(SyncRun.finished_at.desc()).limit(1))
    if latest is None:
        return True
    last = latest.finished_at
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    return now - last >= (timedelta(hours=24) if latest.status == 'success' else timedelta(hours=6))


def start():
    os.chdir(HERE)
    init_database()
    proc = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'main:app',
                             '--host', '127.0.0.1', '--port', '8000'])
    import_process = None
    try:
        url = 'http://127.0.0.1:8000'
        for _ in range(50):
            if proc.poll() is not None:
                raise RuntimeError('Website server exited. Is port 8000 already in use?')
            try:
                with urllib.request.urlopen(url + '/health', timeout=.5):
                    break
            except Exception:
                time.sleep(.2)
        else:
            raise RuntimeError('Website did not start in time')
        print('\nCleveland EMS dashboard is ready: '+url, flush=True)
        webbrowser.open(url)
        while proc.poll() is None:
            if (import_process is None or import_process.poll() is not None) and due_for_refresh():
                print('Refreshing public EMS data in the background. Website stays available.', flush=True)
                import_process = subprocess.Popen([sys.executable, 'ingest.py', '--days', '14'], cwd=HERE)
            time.sleep(60)
    except KeyboardInterrupt:
        pass
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            proc.kill()
        if import_process is not None and import_process.poll() is None:
            import_process.terminate()

if __name__ == '__main__':
    start()
