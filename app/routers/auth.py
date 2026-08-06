from fastapi import APIRouter, Depends, HTTPException, Request, Form
from fastapi.responses import RedirectResponse, HTMLResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app import models
from app.auth import hash_password, verify_password, create_token
from app.core.i18n import resolve_lang, translate


def _err(request, key: str) -> str:
    return translate(resolve_lang(request), key)

router = APIRouter()
from app.core.templating import templates


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@router.post("/login")
def login(request: Request, email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == email).first()
    if not user or not verify_password(password, user.password_hash):
        return templates.TemplateResponse("login.html", {"request": request, "error": _err(request, "auth.err_credentials")})
    token = create_token(user.id)
    response = RedirectResponse("/dashboard", status_code=302)
    response.set_cookie("access_token", token, httponly=True, max_age=30 * 86400)
    return response


@router.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})


@router.post("/register")
def register(request: Request, email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    # bcrypt silently truncates passwords beyond 72 bytes — validate explicitly
    if len(password) < 6:
        return templates.TemplateResponse("register.html", {"request": request, "error": _err(request, "auth.err_password_short")})
    if len(password.encode("utf-8")) > 72:
        return templates.TemplateResponse("register.html", {"request": request, "error": _err(request, "auth.err_password_long")})
    if db.query(models.User).filter(models.User.email == email).first():
        return templates.TemplateResponse("register.html", {"request": request, "error": _err(request, "auth.err_email_taken")})
    user = models.User(email=email, password_hash=hash_password(password), credits=100)  # 100 кредитов при регистрации
    db.add(user)
    db.commit()
    token = create_token(user.id)
    response = RedirectResponse("/dashboard", status_code=302)
    response.set_cookie("access_token", token, httponly=True, max_age=30 * 86400)
    return response


@router.get("/logout")
def logout():
    response = RedirectResponse("/login", status_code=302)
    response.delete_cookie("access_token")
    return response
