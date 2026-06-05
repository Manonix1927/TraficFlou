"""
Celery tasks — отправка GA4 хитов для активных проектов.
Запускается каждую минуту через beat.
"""

import math
import random
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from app.workers.celery_app import celery
from app.core.gcollect import send_hit, pick_weighted

log = logging.getLogger(__name__)


@celery.task
def dispatch_hits():
    """Главная задача: берёт все активные проекты и отправляет порцию хитов."""
    from app.database import SessionLocal
    from app import models

    db = SessionLocal()
    try:
        projects = (
            db.query(models.Project)
            .filter(models.Project.status == "active")
            .all()
        )
        for project in projects:
            user = db.query(models.User).filter(models.User.id == project.user_id).first()
            if not user or user.credits <= 0:
                # Пауза если кредиты закончились
                project.status = "paused"
                db.commit()
                continue

            # Сколько хитов отправить в эту минуту
            hits_per_minute = max(1, math.ceil(project.daily_hits / 1440))
            hits_to_send = min(hits_per_minute, user.credits)

            if hits_to_send <= 0:
                continue

            # Запускаем задачу для этого проекта
            send_project_hits.delay(
                project_id=project.id,
                user_id=user.id,
                hits_count=hits_to_send,
                tid=project.ga_tid,
                site_url=project.site_url,
                sources=project.sources,
                geo=project.geo,
                gtm_id=project.gtm_id,
                device=project.device or "desktop",
            )
    finally:
        db.close()


@celery.task
def send_project_hits(
    project_id: int,
    user_id: int,
    hits_count: int,
    tid: str,
    site_url: str,
    sources: dict,
    geo: dict,
    gtm_id: str = None,
    device: str = "desktop",
):
    """Отправляет hits_count хитов для одного проекта, списывает кредиты."""
    from app.database import SessionLocal
    from app import models

    db = SessionLocal()
    try:
        # Ещё раз проверим кредиты (race condition защита)
        user = db.query(models.User).filter(models.User.id == user_id).first()
        if not user or user.credits < hits_count:
            hits_count = user.credits if user else 0
        if hits_count <= 0:
            return

        # Генерируем задания
        def pick_device(d):
            if isinstance(d, dict) and d:
                return pick_weighted(d)
            # legacy string format
            if d == "mixed":
                return random.choice(["desktop", "mobile", "tablet"])
            return d if d in ("desktop", "mobile", "tablet") else "desktop"

        jobs = []
        for _ in range(hits_count):
            country = pick_weighted(geo)
            source = pick_weighted(sources)
            jobs.append((tid, site_url, country, source, None, gtm_id, pick_device(device)))

        # Параллельная отправка
        ok_count = 0
        logs = []
        with ThreadPoolExecutor(max_workers=10) as ex:
            futures = {ex.submit(send_hit, *j): j for j in jobs}
            for f in as_completed(futures):
                result = f.result()
                if result["status"] == 204:
                    ok_count += 1
                    # Логируем только успешные хиты
                    logs.append(models.HitLog(
                        project_id=project_id,
                        country=result.get("country"),
                        source=result.get("source"),
                        medium="organic",
                        status=204,
                    ))

        # Записываем логи пачкой
        db.bulk_save_objects(logs)

        # Списываем кредиты и обновляем счётчик
        user.credits -= ok_count
        project = db.query(models.Project).filter(models.Project.id == project_id).first()
        if project:
            project.hits_sent += ok_count

        db.commit()
        log.info("Project %s: sent %d/%d hits", project_id, ok_count, hits_count)

    except Exception as e:
        db.rollback()
        log.error("send_project_hits error: %s", e)
    finally:
        db.close()
