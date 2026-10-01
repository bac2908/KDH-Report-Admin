"""Isolated UI test server. Never uses the application's instance directory."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from kdh.app import create_app
from waitress import serve

folder = Path(__file__).resolve().parent.parent / 'test-results' / 'ui-state'
app = create_app({'DATA_DIR':str(folder), 'APP_URL':'http://127.0.0.1:8091',
                  'GOOGLE_CLIENT_ID':'', 'GOOGLE_CLIENT_SECRET':'', 'TESTING':True})
app.extensions['worker'].start()
serve(app,host='127.0.0.1',port=8091,threads=4)
