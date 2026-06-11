import sys
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent
SITE_PACKAGES = PROJECT_DIR / "venv" / "Lib" / "site-packages"
sys.path.insert(0, str(SITE_PACKAGES))

from app import app


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
