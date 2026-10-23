"""Print a correctly signed but EXPIRED JWT for the 401-expired screenshot.

PYTHONPATH=. python code/hw07_expired_token.py
"""

import sys
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from sqlalchemy import select

from src.hw4_database import db_session_basede26
from src.hw4_models import User
from src.hw7_auth import create_access_token

db = db_session_basede26()
user = db.scalar(select(User).where(User.username == "s4098_reader"))
db.close()
print(create_access_token(user, expires_delta=timedelta(minutes=-5)))
