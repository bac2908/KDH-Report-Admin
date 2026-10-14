"""Real localhost HTTP across both apps, isolated SQLite, synthetic provider transport.

Run with Admin's Python and --new-root pointing to the existing New checkout.
Requires New's existing venv. Never reads/writes the runtime Admin database.
"""
import argparse
import http.cookiejar
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from werkzeug.serving import WSGIRequestHandler, make_server
import test_viewer_access as fixtures


class SilentHandler(WSGIRequestHandler):
    def log(self, *args, **kwargs):
        pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class MarketingEndToEnd(unittest.TestCase):
    def setUp(self):
        self.fx = fixtures.SQLiteViewerTests()
        self.fx.setUp()
        self.addCleanup(self.fx.doCleanups)
        self.admin = self.fx.fixture
        self.server = make_server('127.0.0.1', 0, self.admin.app, threaded=True, request_handler=SilentHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop_admin)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        self.base = f'http://127.0.0.1:{port}'
        self.admin_base = f'http://127.0.0.1:{self.server.server_port}'
        self.admin.app.config.update(APP_URL=self.admin_base, REPORT_NEW_BASE_URL=self.base)
        env = {**os.environ, 'APP_ENV': 'production', 'DEBUG': 'false',
               'REPORT_ADMIN_BASE_URL': self.admin_base, 'REPORT_ADMIN_PUBLIC_URL': self.admin_base,
               'REPORT_NEW_PUBLIC_URL': self.base,
               'REPORT_SERVICE_TOKEN': 'test-viewer-service-only', 'REPORT_PREVIEW_ENABLED': 'false'}
        log = open(ROOT / 'test-results' / 'marketing-e2e-new-server.txt', 'w', encoding='utf-8')
        self.addCleanup(log.close)
        python = NEW_ROOT / '.venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
        self.process = subprocess.Popen([str(python), '-m', 'uvicorn', 'main:app', '--host', '127.0.0.1', '--port', str(port)],
            cwd=NEW_ROOT, env=env, stdout=log, stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        self.addCleanup(self.stop_new)
        self.jar = http.cookiejar.CookieJar()
        self.http = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar), NoRedirect)
        for _ in range(100):
            try:
                if self.request('/api/v1/health')[0] == 200:
                    break
            except urllib.error.URLError:
                pass
            if self.process.poll() is not None:
                self.fail('New exited; see isolated server log.')
            time.sleep(.1)
        else:
            self.fail('New did not become ready.')

    def stop_new(self):
        self.process.terminate()
        try:
            self.process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            self.process.kill(); self.process.wait(timeout=5)

    def stop_admin(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(timeout=5)

    def request(self, path, data=None, *, admin=False, json_body=None):
        base = self.admin_base if admin else self.base
        headers = {'Origin': base} if data is not None or json_body is not None else {}
        payload = urllib.parse.urlencode(data).encode() if data is not None else None
        if payload is not None:
            headers['Content-Type'] = 'application/x-www-form-urlencoded'
        if json_body is not None:
            payload = json.dumps(json_body).encode()
            headers.update({'Content-Type': 'application/json', 'X-KDH-Request': '1'})
        try:
            response = self.http.open(urllib.request.Request(base + path, data=payload, headers=headers), timeout=10)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            return response.code, response.read().decode(), {key.lower(): value for key, value in response.headers.items()}

    def login_admin(self, email, password):
        self.assertEqual(self.request('/login')[2]['location'], self.admin_base + '/viewer/reports')
        self.assertEqual(self.request('/api/auth/login', admin=True,
            json_body={'email': email, 'password': password})[0], 200)

    def handoff(self, target, mode='published'):
        scope = {'mode': mode, 'target_id': target}
        if mode == 'published':
            scope['revision'] = 1
        status, _, headers = self.request('/auth/handoff/start?' + urllib.parse.urlencode(scope))
        self.assertEqual(status, 303)
        authorize = urllib.parse.urlsplit(headers['location'])
        self.assertTrue(headers['location'].startswith(self.admin_base + '/viewer/authorize?'))
        status, _, headers = self.request(authorize.path + '?' + authorize.query, admin=True)
        if status != 303:
            return status
        values = {key: items[0] for key, items in urllib.parse.parse_qs(
            urllib.parse.urlsplit(headers['location']).fragment).items()}
        self.assertEqual(self.request('/auth/handoff/callback')[0], 200)
        return self.request('/auth/handoff/callback', json_body=values)[0]

    def test_provider_snapshot_review_publish_and_customer_render_over_http(self):
        # The real adapter normalizes an independently defined test transport.
        original = self.admin.response
        def declining_search(*args, **kwargs):
            result = original(*args, **kwargs)
            if kwargs['json']['startDate'] == '2026-08-29':
                for row in result['rows']:
                    row['clicks'] *= 20; row['impressions'] *= 20
            return result
        self.admin.response = declining_search
        candidate = self.admin.candidate()
        preview = self.admin.client.get('/api/datasets/' + candidate).json['marketing']['preview']
        self.assertGreater(len(preview['opportunity_candidates']), 0)
        selected = preview['opportunity_candidates'][0]['id']
        approval = self.admin.approve(candidate, approved_opportunity_ids=[selected])
        self.assertEqual(approval.status_code, 201, approval.json)
        checks = self.admin.check(candidate)
        released = self.admin.client.post(f'/api/marketing/release-candidates/{candidate}/release-snapshots',
            json={'expected_approval_id': approval.json['approval_id'], 'expected_candidate_sha256': checks['candidate_sha256']},
            headers=self.admin.headers)
        self.assertEqual(released.status_code, 201, released.json)
        self.fx.release_id = released.json['dataset_id']
        report = self.fx.bundle()
        self.fx.grant(report)
        self.login_admin('viewer@example.test', 'Viewer-test-password-123')
        path = '/reports/' + report + '?revision=1'
        self.assertEqual(self.handoff(report), 404)  # Draft remains private even with a grant.
        self.assertEqual(self.fx.publish(report, 'final').status_code, 200)
        self.assertEqual(self.handoff(report), 200)
        status, html, headers = self.request(path)
        self.assertEqual(status, 200, html[:500])
        self.assertIn('gsc.clicks', html)
        self.assertIn('360', html)  # Exact previous total; never read from mock renderer.
        self.assertIn('60', html)
        self.assertIn(preview['opportunity_candidates'][0]['title'], html)
        self.assertIn('data-bundle-chart', html)
        self.assertIn('no-store', headers['cache-control'])
        self.assertNotIn('test-viewer-service-only', html)
        self.assertNotIn('test-only-access', html)
        self.assertEqual(self.request('/internal-preview/' + candidate)[0], 403)
        self.assertEqual(self.request('/overview')[0], 404)
        self.assertEqual(self.request('/reports/' + report + '?revision=2')[0], 404)
        self.fx.grant(report, active=False)
        self.assertEqual(self.request(path)[0], 404)
        self.jar.clear()
        self.login_admin('review-admin@example.test', 'Review-Password-12345')
        self.assertEqual(self.handoff(candidate, mode='preview'), 200)
        status, html, _ = self.request('/internal-preview/' + candidate)
        self.assertEqual(status, 200)
        self.assertIn('CHƯA XUẤT BẢN', html)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--new-root', required=True, type=Path)
    args = parser.parse_args()
    NEW_ROOT = args.new_root.resolve()
    unittest.main(argv=[sys.argv[0]], verbosity=2)
