import json
import math
import random
import re
import requests as http_requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from fastapi import APIRouter, Depends, Request, Form, HTTPException, BackgroundTasks
from fastapi.responses import RedirectResponse, HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.database import get_db
from app import models
from app.auth import get_current_user
from app.core.gcollect import send_hit, pick_weighted

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

SOURCE_LABELS = {
    "google_organic": "Google Organic", "bing_organic": "Bing Organic",
    "duckduckgo_organic": "DuckDuckGo", "yahoo_organic": "Yahoo",
    "youtube_organic": "YouTube", "google_cpc": "Google Ads",
    "instagram": "Instagram", "facebook": "Facebook",
    "linkedin": "LinkedIn", "twitter": "Twitter / X",
    "pinterest": "Pinterest", "tiktok": "TikTok",
    "chatgpt": "ChatGPT", "perplexity": "Perplexity AI",
    "gemini": "Gemini", "copilot": "Copilot", "grok": "Grok",
    "whatsapp": "WhatsApp", "telegram": "Telegram",
    "email": "Email", "direct": "Direct", "referral": "Referral",
    # legacy keys
    "organic": "Google Organic", "social": "Social", "cpc": "Google Ads",
}

COUNTRIES = [
    ("UA", "Ukraine"), ("DE", "Germany"), ("PL", "Poland"), ("FR", "France"),
    ("IT", "Italy"), ("ES", "Spain"), ("CZ", "Czech Republic"), ("SK", "Slovakia"),
    ("HU", "Hungary"), ("RO", "Romania"), ("GB", "United Kingdom"), ("NL", "Netherlands"),
    ("BE", "Belgium"), ("AT", "Austria"), ("CH", "Switzerland"), ("SE", "Sweden"),
    ("NO", "Norway"), ("DK", "Denmark"), ("FI", "Finland"), ("PT", "Portugal"),
    ("GR", "Greece"), ("BG", "Bulgaria"), ("HR", "Croatia"), ("RS", "Serbia"),
    ("TR", "Turkey"), ("US", "United States"),
]


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    projects = db.query(models.Project).filter(models.Project.user_id == user.id).all()
    return templates.TemplateResponse("dashboard.html", {
        "request": request, "user": user, "projects": projects,
    })


@router.get("/api/detect-ga", response_class=JSONResponse)
def detect_ga(url: str, user: models.User = Depends(get_current_user)):
    """Fetches the page and extracts GA4/GTM IDs from HTML."""
    try:
        if not url.startswith("http"):
            url = "https://" + url
        resp = http_requests.get(url, timeout=10, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36"
        })
        html = resp.text
        ga4_ids = list(set(re.findall(r'G-[A-Z0-9]{6,}', html)))
        gtm_ids = list(set(re.findall(r'GTM-[A-Z0-9]{4,}', html)))
        return {
            "ok": True,
            "ga4_id": ga4_ids[0] if ga4_ids else None,
            "gtm_id": gtm_ids[0] if gtm_ids else None,
            "all_ga4": ga4_ids,
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.get("/projects/create", response_class=HTMLResponse)
def create_project_page(request: Request, user: models.User = Depends(get_current_user)):
    return templates.TemplateResponse("project_create.html", {
        "request": request, "user": user, "countries": COUNTRIES,
    })


@router.post("/projects/create")
def create_project(
    request: Request,
    name: str = Form(...),
    site_url: str = Form(...),
    ga_tid: str = Form(...),
    gtm_id: str = Form(""),
    daily_hits: int = Form(100),
    device_desktop: int = Form(100),
    device_mobile: int = Form(0),
    device_tablet: int = Form(0),
    source_keys: list = Form(...),
    source_percents: list = Form(...),
    geo_countries: list = Form(...),
    geo_percents: list = Form(...),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    sources = {k: int(p) for k, p in zip(source_keys, source_percents) if int(p) > 0}
    geo = {c: int(p) for c, p in zip(geo_countries, geo_percents) if int(p) > 0}
    device = {k: v for k, v in [("desktop", device_desktop), ("mobile", device_mobile), ("tablet", device_tablet)] if v > 0}
    # Fallbacks — empty dicts would later crash pick_weighted()
    if not device:
        device = {"desktop": 100}
    if not sources:
        sources = {"google_organic": 100}
    if not geo:
        geo = {"UA": 100}

    project = models.Project(
        user_id=user.id,
        name=name,
        site_url=site_url,
        ga_tid=ga_tid,
        gtm_id=gtm_id or None,
        daily_hits=daily_hits,
        device=device,
        sources=sources,
        geo=geo,
        status="paused",
    )
    db.add(project)
    db.commit()
    return RedirectResponse(f"/projects/{project.id}", status_code=302)


@router.get("/projects/{project_id}", response_class=HTMLResponse)
def project_detail(
    project_id: int, request: Request,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    project = db.query(models.Project).filter(
        models.Project.id == project_id,
        models.Project.user_id == user.id,
    ).first()
    if not project:
        raise HTTPException(404)

    # Статистика за последние 24ч — только успешные хиты (status=204)
    from sqlalchemy import func
    from datetime import datetime, timedelta
    since = datetime.utcnow() - timedelta(hours=24)
    base = db.query(models.HitLog).filter(
        models.HitLog.project_id == project_id,
        models.HitLog.created_at >= since,
        models.HitLog.status == 204,
    )
    stats_country = (
        base.with_entities(models.HitLog.country, func.count(models.HitLog.id))
        .group_by(models.HitLog.country).all()
    )
    stats_source = (
        base.with_entities(models.HitLog.source, func.count(models.HitLog.id))
        .filter(models.HitLog.source.isnot(None), models.HitLog.source != "")
        .group_by(models.HitLog.source)
        .order_by(func.count(models.HitLog.id).desc())
        .all()
    )

    # Map source keys to readable labels
    stats_source_labeled = [
        (SOURCE_LABELS.get(src, src), count)
        for src, count in stats_source
    ]

    return templates.TemplateResponse("project_detail.html", {
        "request": request, "user": user, "project": project,
        "countries": COUNTRIES,
        "stats_country": stats_country,
        "stats_source": stats_source_labeled,
    })


@router.post("/projects/{project_id}/toggle")
def toggle_project(
    project_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    project = db.query(models.Project).filter(
        models.Project.id == project_id, models.Project.user_id == user.id
    ).first()
    if not project:
        raise HTTPException(404)
    if project.status == "active":
        project.status = "paused"
    else:
        if user.credits <= 0:
            raise HTTPException(400, "Недостаточно кредитов")
        project.status = "active"
    db.commit()
    return RedirectResponse(f"/projects/{project_id}", status_code=302)


@router.post("/projects/{project_id}/update")
def update_project(
    project_id: int,
    request: Request,
    name: str = Form(...),
    daily_hits: int = Form(100),
    device_desktop: int = Form(0),
    device_mobile: int = Form(0),
    device_tablet: int = Form(0),
    source_keys: list = Form(...),
    source_percents: list = Form(...),
    geo_countries: list = Form(...),
    geo_percents: list = Form(...),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    project = db.query(models.Project).filter(
        models.Project.id == project_id, models.Project.user_id == user.id
    ).first()
    if not project:
        raise HTTPException(404)

    device = {k: v for k, v in [("desktop", device_desktop), ("mobile", device_mobile), ("tablet", device_tablet)] if v > 0}
    sources = {k: int(p) for k, p in zip(source_keys, source_percents) if int(p) > 0}
    geo = {c: int(p) for c, p in zip(geo_countries, geo_percents) if int(p) > 0}
    # Fallbacks — empty dicts would later crash pick_weighted()
    if not device:
        device = {"desktop": 100}
    if not sources:
        sources = {"google_organic": 100}
    if not geo:
        geo = {"UA": 100}

    from sqlalchemy.orm.attributes import flag_modified
    project.name = name
    project.daily_hits = daily_hits
    project.device = device
    project.sources = sources
    project.geo = geo
    flag_modified(project, "device")
    flag_modified(project, "sources")
    flag_modified(project, "geo")
    db.commit()
    return RedirectResponse(f"/projects/{project_id}", status_code=302)


def _send_hits_sync(project_id: int, user_id: int, count: int, tid: str, site_url: str, sources: dict, geo: dict, gtm_id: str, device=None):
    """Синхронная отправка хитов — используется для немедленного запуска."""
    from app.database import SessionLocal
    from app.core.credits import reserve_credits, refund_credits
    if not sources or not geo:
        return
    db = SessionLocal()
    try:
        # Атомарно резервируем кредиты до отправки (защита от overspend)
        reserved = reserve_credits(db, user_id, count)
        if reserved <= 0:
            return
        count = reserved

        def pick_dev(d):
            if isinstance(d, dict) and d:
                return pick_weighted(d)
            if d == "mixed":
                return random.choice(["desktop", "mobile", "tablet"])
            return d if d in ("desktop", "mobile", "tablet") else "desktop"

        jobs = [(tid, site_url, pick_weighted(geo), pick_weighted(sources), None, gtm_id, pick_dev(device or "desktop")) for _ in range(count)]
        ok = 0
        logs = []
        with ThreadPoolExecutor(max_workers=10) as ex:
            futures = {ex.submit(send_hit, *j): j for j in jobs}
            for f in as_completed(futures):
                r = f.result()
                if r["status"] == 204:
                    ok += 1
                    logs.append(models.HitLog(
                        project_id=project_id, country=r.get("country"),
                        source=r.get("source"), medium=r.get("medium", "none"), status=204,
                    ))
        db.bulk_save_objects(logs)
        # Возвращаем кредиты за неотправленные хиты
        refund_credits(db, user_id, count - ok)
        project = db.query(models.Project).filter(models.Project.id == project_id).first()
        if project: project.hits_sent = (project.hits_sent or 0) + ok
        db.commit()
    finally:
        db.close()


@router.post("/projects/{project_id}/send-now")
def send_now(
    project_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    project = db.query(models.Project).filter(
        models.Project.id == project_id, models.Project.user_id == user.id
    ).first()
    if not project:
        raise HTTPException(404)
    if user.credits <= 0:
        raise HTTPException(400, "Недостаточно кредитов")
    if not project.sources or not project.geo:
        raise HTTPException(400, "Настройте источники трафика и гео-таргетинг")

    # Порция за 1 минуту
    count = min(max(1, math.ceil(project.daily_hits / 1440)), user.credits, 50)

    background_tasks.add_task(
        _send_hits_sync,
        project_id=project.id, user_id=user.id, count=count,
        tid=project.ga_tid, site_url=project.site_url,
        sources=project.sources, geo=project.geo, gtm_id=project.gtm_id,
        device=project.device,
    )
    return JSONResponse({"ok": True, "count": count})


@router.post("/projects/{project_id}/delete")
def delete_project(
    project_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    project = db.query(models.Project).filter(
        models.Project.id == project_id, models.Project.user_id == user.id
    ).first()
    if not project:
        raise HTTPException(404)
    # hit_logs are removed via ORM cascade (Project.hit_logs delete-orphan)
    db.delete(project)
    db.commit()
    return RedirectResponse("/dashboard", status_code=302)
