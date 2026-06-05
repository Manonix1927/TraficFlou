from celery import Celery
import os

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery = Celery(
    "traffic",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["app.workers.tasks"],
)

celery.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    beat_schedule={
        # Каждую минуту отправляем порцию хитов для всех активных проектов
        "dispatch-hits-every-minute": {
            "task": "app.workers.tasks.dispatch_hits",
            "schedule": 60.0,
        },
    },
)
