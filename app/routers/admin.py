from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.database import get_db
from app import models
from app.auth import get_current_user

router = APIRouter(prefix="/admin")
templates = Jinja2Templates(directory="app/templates")


def require_admin(user: models.User = Depends(get_current_user)) -> models.User:
    if not user.is_admin:
        raise HTTPException(403, "Forbidden")
    return user


# ── Users list ────────────────────────────────────────────────
@router.get("", response_class=HTMLResponse)
def admin_index(
    request: Request,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_admin),
):
    users = db.query(models.User).order_by(models.User.created_at.desc()).all()
    return templates.TemplateResponse("admin/users.html", {
        "request": request, "user": user, "users": users,
    })


# ── User detail ───────────────────────────────────────────────
@router.get("/users/{uid}", response_class=HTMLResponse)
def admin_user(
    uid: int, request: Request,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_admin),
):
    target = db.query(models.User).filter(models.User.id == uid).first()
    if not target:
        raise HTTPException(404)
    projects = db.query(models.Project).filter(models.Project.user_id == uid).all()
    return templates.TemplateResponse("admin/user_detail.html", {
        "request": request, "user": user, "target": target, "projects": projects,
    })


# ── Add credits ───────────────────────────────────────────────
@router.post("/users/{uid}/credits")
def add_credits(
    uid: int,
    amount: int = Form(...),
    db: Session = Depends(get_db),
    user: models.User = Depends(require_admin),
):
    target = db.query(models.User).filter(models.User.id == uid).first()
    if not target:
        raise HTTPException(404)
    target.credits += amount
    tx = models.CreditTransaction(
        user_id=uid,
        amount=amount,
        description=f"Admin добавил {amount} кредитов",
    )
    db.add(tx)
    db.commit()
    return RedirectResponse(f"/admin/users/{uid}", status_code=302)


# ── Delete user ───────────────────────────────────────────────
@router.post("/users/{uid}/delete")
def delete_user(
    uid: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_admin),
):
    if uid == user.id:
        raise HTTPException(400, "Cannot delete yourself")
    target = db.query(models.User).filter(models.User.id == uid).first()
    if not target:
        raise HTTPException(404)
    db.query(models.HitLog).filter(
        models.HitLog.project_id.in_(
            db.query(models.Project.id).filter(models.Project.user_id == uid)
        )
    ).delete(synchronize_session=False)
    db.query(models.Project).filter(models.Project.user_id == uid).delete()
    db.query(models.CreditTransaction).filter(models.CreditTransaction.user_id == uid).delete()
    db.delete(target)
    db.commit()
    return RedirectResponse("/admin", status_code=302)


# ── Toggle project ────────────────────────────────────────────
@router.post("/projects/{pid}/toggle")
def admin_toggle_project(
    pid: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_admin),
):
    project = db.query(models.Project).filter(models.Project.id == pid).first()
    if not project:
        raise HTTPException(404)
    project.status = "paused" if project.status == "active" else "active"
    db.commit()
    return RedirectResponse(f"/admin/users/{project.user_id}", status_code=302)


# ── Edit project ──────────────────────────────────────────────
@router.post("/projects/{pid}/update")
def admin_update_project(
    pid: int,
    daily_hits: int = Form(...),
    status: str = Form(...),
    db: Session = Depends(get_db),
    user: models.User = Depends(require_admin),
):
    project = db.query(models.Project).filter(models.Project.id == pid).first()
    if not project:
        raise HTTPException(404)
    project.daily_hits = daily_hits
    project.status = status
    db.commit()
    return RedirectResponse(f"/admin/users/{project.user_id}", status_code=302)


# ── Delete project ────────────────────────────────────────────
@router.post("/projects/{pid}/delete")
def admin_delete_project(
    pid: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_admin),
):
    project = db.query(models.Project).filter(models.Project.id == pid).first()
    if not project:
        raise HTTPException(404)
    uid = project.user_id
    db.query(models.HitLog).filter(models.HitLog.project_id == pid).delete()
    db.delete(project)
    db.commit()
    return RedirectResponse(f"/admin/users/{uid}", status_code=302)
