from pathlib import Path
import json
import psycopg


ROOT = Path(__file__).resolve().parents[1]

CREDENTIAL_FILE = (
    ROOT
    / "database"
    / ".local"
    / "credentials.json"
)


def get_connection():
    if not CREDENTIAL_FILE.exists():
        raise FileNotFoundError(
            "Khong tim thay credentials.json. "
            "Hay setup database truoc."
        )

    config = json.loads(
        CREDENTIAL_FILE.read_text(
            encoding="utf-8"
        )
    )

    return psycopg.connect(
        host="127.0.0.1",
        port=config.get("port", 5433),
        dbname="geopulse",
        user="geopulse",
        password=config["admin_password"],
    )