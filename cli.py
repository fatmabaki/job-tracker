import sys
from app.main import load_settings
from app.services.tracker import Tracker

if __name__ == "__main__":
    tracker = Tracker(load_settings())
    if sys.argv[1:] == ["migrate"]: tracker.migrate()
    elif sys.argv[1:] == ["seed"]: tracker.seed()
    else: raise SystemExit("Usage: python -m app.cli migrate|seed")
