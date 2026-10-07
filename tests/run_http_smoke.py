"""One command: a fresh local server, the HTTP smoke flow, then clean shutdown."""
import secrets
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from waitress import create_server, wasyncore
from kdh.app import create_app
from http_smoke import main as smoke


def main():
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    folder = ROOT / 'test-results' / ('http-smoke-' + stamp + '-' + secrets.token_hex(3))
    app = create_app({'DATA_DIR': str(folder), 'APP_URL': 'http://127.0.0.1:8091',
                      'DATABASE_URL':'', 'JOB_MODE':'worker', 'ENCRYPTION_KEY':'',
                      'INITIAL_ADMIN_EMAIL':'', 'INITIAL_ADMIN_PASSWORD':'',
                      'GOOGLE_CLIENT_ID': '', 'GOOGLE_CLIENT_SECRET': '', 'COOKIE_SECURE': False,
                      'LEGACY_REPORT_DIR': str(folder / 'unused-legacy'), 'TESTING': True})
    socket_map = {}
    # Bind first: if 8091 is in use, fail without sending requests to an unknown server.
    server = create_server(app, host='127.0.0.1', port=8091, threads=4, map=socket_map,
                           asyncore_loop_timeout=.1)
    worker = app.extensions['worker']
    thread = threading.Thread(target=server.run, name='http-smoke-server', daemon=True)
    try:
        worker.start()
        thread.start()
        smoke()
        print('Isolated test artifacts: ' + str(folder.relative_to(ROOT)))
    finally:
        worker.stopping.set()
        if worker.thread:
            worker.thread.join(timeout=5)
        server.task_dispatcher.shutdown()
        wasyncore.close_all(socket_map)
        thread.join(timeout=5)


if __name__ == '__main__':
    main()
