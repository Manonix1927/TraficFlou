from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from app.database import Base, engine
from app.routers import auth, projects, admin
from sqlalchemy import text

Base.metadata.create_all(bind=engine)

# Safe column migrations — add missing columns without dropping data.
# ВАЖНО: не использовать ":" вплотную к слову/числу внутри SQL-строк —
# SQLAlchemy text() примет это за bind-параметр и запрос молча упадёт
# в except ниже. Поэтому '{"desktop": 100}' пишем с пробелом после ":".
def run_migrations():
    is_postgres = engine.dialect.name == "postgresql"

    common = [
        # Speeds up the per-project 24h stats query
        "CREATE INDEX IF NOT EXISTS ix_hitlog_project_created ON hit_logs (project_id, created_at)",
    ]

    if is_postgres:
        migrations = [
            "ALTER TABLE projects ADD COLUMN IF NOT EXISTS gtm_id VARCHAR",
            # Колонка device могла вообще не создаться на старых базах
            "ALTER TABLE projects ADD COLUMN IF NOT EXISTS device JSONB",
            # Исторически device создавался как VARCHAR ('desktop'/'mobile'/
            # 'mixed'). Пока тип не сконвертирован, ORM читает строку вместо
            # dict, и таргетинг устройств молча работает как 100% desktop.
            """DO $$
            BEGIN
              IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'projects' AND column_name = 'device'
                AND data_type IN ('character varying', 'text', 'character')
              ) THEN
                ALTER TABLE projects ALTER COLUMN device DROP DEFAULT;
                ALTER TABLE projects ALTER COLUMN device TYPE JSONB USING
                  CASE
                    WHEN device IS NULL THEN jsonb_build_object('desktop', 100)
                    WHEN device LIKE '{%' THEN device::jsonb
                    WHEN device = 'mobile' THEN jsonb_build_object('mobile', 100)
                    WHEN device = 'tablet' THEN jsonb_build_object('tablet', 100)
                    WHEN device = 'mixed' THEN
                      jsonb_build_object('desktop', 34, 'mobile', 33, 'tablet', 33)
                    ELSE jsonb_build_object('desktop', 100)
                  END;
              END IF;
            END $$""",
            # Только пустые значения — сохранённые настройки не трогаем
            "UPDATE projects SET device = jsonb_build_object('desktop', 100) WHERE device IS NULL",
        ] + common
    else:
        # SQLite: ADD COLUMN не поддерживает IF NOT EXISTS — если колонка
        # уже есть, запрос упадёт и будет проглочен except ниже.
        migrations = [
            "ALTER TABLE projects ADD COLUMN gtm_id VARCHAR",
            "ALTER TABLE projects ADD COLUMN device JSON",
            "UPDATE projects SET device = '{\"desktop\": 100}' WHERE device IS NULL",
        ] + common

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
