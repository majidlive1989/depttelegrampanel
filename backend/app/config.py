import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("DATA_DIR", BASE_DIR / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = Path(os.getenv("DB_PATH", DATA_DIR / "debt_collector.db"))

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_ADMIN_IDS = {
    int(x.strip())
    for x in os.getenv("TELEGRAM_ADMIN_IDS", "").split(",")
    if x.strip().lstrip("-").isdigit()
}
APP_TIMEZONE = os.getenv("APP_TIMEZONE", "Asia/Tehran")
FOLLOWUP_INTERVAL_SECONDS = max(30, int(os.getenv("FOLLOWUP_INTERVAL_SECONDS", "60")))
SEND_COOLDOWN_MINUTES = max(0, int(os.getenv("SEND_COOLDOWN_MINUTES", "30")))
