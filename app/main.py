from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from app.database import Base, engine
from app.routers import auth, projects, admin
from sqlalchemy import text

Base.metadata.create_all(bind=engine)

# Safe column migrations — add missing columns without dropping data
def run_migrations():
    migrations = [
        "ALTER TABLE projects ADD COLUMN IF NOT EXISTS gtm_id VARCHAR",
        # Convert device string → JSON (safe: only runs if column exists as varchar)
        """DO $$
        BEGIN
          IF EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name='projects' AND column_name='device'
            AND data_type IN ('character varying','text','character')
          ) THEN
            ALTER TABLE projects ALTER COLUMN device TYPE JSONB USING
              CASE device
                WHEN 'mobile' THEN '{\"mobile\":100}'::jsonb
                WHEN 'mixed'  THEN '{\"desktop\":50,\"mobile\":50}'::jsonb
                ELSE '{\"desktop\":100}'::jsonb
              END;
          END IF;
        END $$""",
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
app.include_router(admin.router)


@app.get("/")
def root():
    return RedirectResponse("/dashboard")
