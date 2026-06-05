from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from app.database import Base, engine
from app.routers import auth, projects
from sqlalchemy import text

Base.metadata.create_all(bind=engine)

# Safe column migrations — add missing columns without dropping data
def run_migrations():
    migrations = [
        "ALTER TABLE projects ADD COLUMN IF NOT EXISTS device VARCHAR DEFAULT 'desktop'",
        "ALTER TABLE projects ADD COLUMN IF NOT EXISTS gtm_id VARCHAR",
    ]
    with engine.connect() as conn:
        for sql in migrations:
            try:
                conn.execute(text(sql))
                conn.commit()
            except Exception:
                conn.rollback()

try:
    run_migrations()
except Exception:
    pass  # SQLite doesn't support IF NOT EXISTS — fine for local dev

app = FastAPI(title="TrafficFlow")

app.include_router(auth.router)
app.include_router(projects.router)


@app.get("/")
def root():
    return RedirectResponse("/dashboard")
