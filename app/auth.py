from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
import bcrypt
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session
from app.database import get_db
from app import models
import os

_INSECURE_DEFAULTS = {
    None, "",
    "change-me-in-production",
    "change-me-to-random-string-min-32-chars",
    "trafficflow-secret-key-change-in-production",
}
SECRET_KEY = os.getenv("SECRET_KEY")
if SECRET_KEY in _INSECURE_DEFAULTS:
    # On a real deployment (Postgres) refuse to start with a guessable key —
    # otherwise anyone can forge JWTs. Local SQLite dev gets a dev fallback.
    if os.getenv("DATABASE_URL", "").startswith(("postgres://", "postgresql://")):
        raise RuntimeError(
            "SECRET_KEY env var must be set to a strong random value in production"
        )
    SECRET_KEY = "dev-only-insecure-key-do-not-use-in-production"

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 30


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def create_token(user_id: int) -> str:
    expire = datetime.utcnow() + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
    return jwt.encode({"sub": str(user_id), "exp": expire}, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
) -> models.User:
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=302, headers={"Location": "/login"})
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = int(payload.get("sub"))
    except (JWTError, TypeError):
        raise HTTPException(status_code=302, headers={"Location": "/login"})
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=302, headers={"Location": "/login"})
    return user
