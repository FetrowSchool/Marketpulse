"""Read-only persistence audit; never changes observations."""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services.database import Database

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    result = Database(parser.parse_args().db).verify_integrity()
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["ok"] else 1)
