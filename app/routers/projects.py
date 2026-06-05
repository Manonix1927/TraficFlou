import json
import math
import random
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
    sources_organic: int = Form(40),
    sources_social: int = Form(25),
    sources_direct: int = Form(20),
    sources_referral: int = Form(15),
    geo_countries: list = Form(...),
    geo_percents: list = Form(...),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    sources = {
        "organic": sources_organic,
        "social": sources_social,
        "direct": sources_direct,
        "referral": sources_referral,
    }
    geo = {c: int(p) for c, p in zip(geo_countries, geo_percents) if int(p) > 0}

    project = models.Project(
        user_id=user.id,
        name=name,
        site_url=site_url,
        ga_tid=ga_tid,
        gtm_id=gtm_id or None,
        daily_hits=daily_hits,
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

    # Статистика за последние 24ч
    from sqlalchemy import func
    from datetime import datetime, timedelta
    since = datetime.utcnow() - timedelta(hours=24)
    stats_country = (
        db.query(models.HitLog.country, func.count(models.HitLog.id))
        .filter(models.HitLog.project_id == project_id, models.HitLog.created_at >= since)
        .group_by(models.HitLog.country).all()
    )
    stats_source = (
        db.query(models.HitLog.source, func.count(models.HitLog.id))
        .filter(models.HitLog.project_id == project_id, models.HitLog.created_at >= since)
        .group_by(models.HitLog.source).all()
    )

    return templates.TemplateResponse("project_detail.html", {
        "request": request, "user": user, "project": project,
        "countries": COUNTRIES,
        "stats_country": stats_country,
        "stats_source": stats_source,
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
    sources_organic: int = Form(40),
    sources_social: int = Form(25),
    sources_direct: int = Form(20),
    sources_referral: int = Form(15),
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

    project.name = name
    project.daily_hits = daily_hits
    project.sources = {
        "organic": sources_organic, "social": sources_social,
        "direct": sources_direct, "referral": sources_referral,
    }
    project.geo = {c: int(p) for c, p in zip(geo_countries, geo_percents) if int(p) > 0}
    db.commit()
    return RedirectResponse(f"/projects/{project_id}", status_code=302)


def _send_hits_sync(project_id: int, user_id: int, count: int, tid: str, site_url: str, sources: dict, geo: dict, gtm_id: str):
    """Синхронная отправка хитов — используется для немедленного запуска."""
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        jobs = [(tid, site_url, pick_weighted(geo), pick_weighted(sources), None, gtm_id) for _ in range(count)]
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
                    source=r.get("source"), medium="organic", status=r.get("status", 0),
                ))
        db.bulk_save_objects(logs)
        user = db.query(models.User).filter(models.User.id == user_id).first()
        project = db.query(models.Project).filter(models.Project.id == project_id).first()
        if user: user.credits = max(0, user.credits - ok)
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

    # Порция за 1 минуту
    count = min(max(1, math.ceil(project.daily_hits / 1440)), user.credits, 50)

    background_tasks.add_task(
        _send_hits_sync,
        project_id=project.id, user_id=user.id, count=count,
        tid=project.ga_tid, site_url=project.site_url,
        sources=project.sources, geo=project.geo, gtm_id=project.gtm_id,
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
    db.delete(project)
    db.commit()
    return RedirectResponse("/dashboard", status_code=302)
