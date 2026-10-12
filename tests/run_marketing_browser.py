"""Optional browser QA with an existing Playwright install and isolated app fixtures.

No runtime DB, provider network, .env edit, or production dependency installation.
"""
import argparse
import json
from pathlib import Path
import subprocess

import run_marketing_e2e as e2e


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--new-root', required=True, type=Path)
    parser.add_argument('--playwright-module', required=True, type=Path)
    args = parser.parse_args()
    e2e.NEW_ROOT = args.new_root.resolve()
    output = e2e.ROOT / 'test-results' / 'marketing-browser'
    output.mkdir(parents=True, exist_ok=True)
    fixture = e2e.MarketingEndToEnd()
    try:
        fixture.setUp()
        original = fixture.admin.response

        def declining_search(*args, **kwargs):
            result = original(*args, **kwargs)
            if kwargs['json']['startDate'] == '2026-08-29':
                for row in result['rows']:
                    row['clicks'] *= 20
                    row['impressions'] *= 20
            return result

        fixture.admin.response = declining_search
        run = fixture.admin.sync()
        fixture.admin.app.config['REPORT_NEW_BASE_URL'] = fixture.base
        config = {'admin': f'http://127.0.0.1:{fixture.server.server_port}',
                  'new': fixture.base, 'asset': run['asset_id'],
                  'viewer': fixture.fx.viewer_id, 'output': str(output)}
        fixture.admin.app.config['APP_URL'] = config['admin']
        result = subprocess.run(['node', str(e2e.ROOT / 'tests' / 'marketing.browser.cjs'),
                                 str(args.playwright_module.resolve())],
                                input=json.dumps(config), text=True, encoding='utf-8',
                                timeout=180, check=False)
        return result.returncode
    finally:
        fixture.doCleanups()


if __name__ == '__main__':
    raise SystemExit(main())
