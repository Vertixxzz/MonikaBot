#import os
#from typing import List

#try:
#    from dotenv import load_dotenv  # pip install python-dotenv
#    load_dotenv()
#except Exception:
#    pass

#def _require(name: str) -> str:
#    v = os.getenv(name)
#    if not v:
#        raise RuntimeError(f"Missing env var: {name}")
#    return v

#def _list(name: str) -> List[int | str]:
#    raw = os.getenv(name, "")
#    parts = [p.strip() for p in raw.replace(" ", ",").split(",") if p.strip()]
#    out = []
#    for p in parts:
#        try:
#            out.append(int(p))
#       except ValueError:
#            out.append(p)
#    return out

#MONIKATOKEN   = _require("MONIKATOKEN")
#SAYORITOKEN   = _require("SAYORITOKEN")
#TARGET_CHAT_ID = int(os.getenv("TARGET_CHAT_ID", "0"))
#BAN_LIST      = _list("BAN_LIST")
#ADMIN_LIST    = _list("ADMIN_LIST")
#BOOSTERS_LIST = _list("BOOSTERS_LIST")

#DB_USER = os.getenv("DB_USER", "postgres")
#DB_PASSWORD = os.getenv("DB_PASSWORD", "123")
#DB_NAME = os.getenv("DB_NAME", "postgres")
#DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
#DB_PORT = int(os.getenv("DB_PORT", "5432"))

#OWM_API_KEY  = os.getenv("OWM_API_KEY", "")
#SECRET_TOKEN = os.getenv("SECRET_TOKEN", "dev-secret")
#WEBHOOK_URL  = os.getenv("WEBHOOK_URL", "")
#WEBHOOK_PATH = os.getenv("WEBHOOK_PATH", "/telegram/webhook")