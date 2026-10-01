"""Place Flask static assets on Vercel's CDN without duplicating source files."""
import shutil
from pathlib import Path

root = Path(__file__).resolve().parents[1]
shutil.copytree(root / 'static', root / 'public' / 'static', dirs_exist_ok=True)
