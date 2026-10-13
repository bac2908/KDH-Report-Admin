"""Browser E2E fixture: temporary SQLite, synthetic provider transport only."""
import json
import sys
from pathlib import Path
from waitress import serve

root = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(root), str(root / 'tests')]
from test_viewer_handoff import SQLiteHandoffTests

case = SQLiteHandoffTests()
case.setUp()
case.app.config.update(APP_URL='http://localhost:8093', REPORT_NEW_BASE_URL='http://localhost:8084')
state = {'report_id': case.report_id, 'revision':1, 'candidate_id':case.candidate_id}
output = root / 'test-results' / 'dashboard-binding'
output.mkdir(parents=True, exist_ok=True)
(output / 'e2e-state.json').write_text(json.dumps(state), encoding='utf-8')
print('Fixture Admin at http://localhost:8093 (temporary database)', flush=True)
try:
    serve(case.app, host='127.0.0.1', port=8093, threads=6)
finally:
    case.doCleanups()
