"""
Баланс і поповнення: вибір плану → замовлення → реквізити ФОП.

Оплата ручна (переказ на рахунок ФОП), тому кредити нараховує адмін
після підтвердження надходження коштів — див. admin.confirm_order.
"""

from datetime import datetime

from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse
from sqlalchemy.orm import Session

from app import models
from app.auth import get_current_user
from app.core.i18n import resolve_lang
from app.core.plans import (
    CURRENCY,
    CURRENCY_SYMBOL,
    FOP_REQUISITES,
    PLANS,
    get_plan,
    plan_features,
    plan_name,
    requisites_ready,
)
from app.core.templating import templates
from app.database import get_db

router = APIRouter()


def _localized_plans(lang: str) -> list:
    """Плани з підставленими під мову назвами та перевагами."""
    return [
        {
            "key": p["key"],
            "name": plan_name(p, lang),
            "credits": p["credits"],
            "price": p["price"],
            "popular": p.get("popular", False),
            "features": plan_features(p, lang),
            # ціна за 1000 кредитів — щоб було видно вигоду більших планів
            "per_1k": round(p["price"] / (p["credits"] / 1000), 2),
        }
        for p in PLANS
    ]


@router.get("/billing", response_class=HTMLResponse)
def billing_page(
    request: Request,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    lang = resolve_lang(request)
    orders = (
        db.query(models.PaymentOrder)
        .filter(models.PaymentOrder.user_id == user.id)
        .order_by(models.PaymentOrder.id.desc())
        .limit(20)
        .all()
    )
    return templates.TemplateResponse("billing.html", {
        "request": request,
        "user": user,
        "plans": _localized_plans(lang),
        "orders": orders,
        "currency": CURRENCY,
        "symbol": CURRENCY_SYMBOL,
    })


@router.post("/billing/order")
def create_order(
    request: Request,
    plan_key: str = Form(...),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    plan = get_plan(plan_key)
    if not plan:
        raise HTTPException(400, "Невідомий план")

    lang = resolve_lang(request)
    order = models.PaymentOrder(
        user_id=user.id,
        plan_key=plan["key"],
        plan_name=plan_name(plan, lang),
        credits=plan["credits"],
        amount=plan["price"],
        currency=CURRENCY,
        status="pending",
    )
    db.add(order)
    db.commit()
    return RedirectResponse(f"/billing/order/{order.id}", status_code=302)


@router.get("/billing/order/{order_id}", response_class=HTMLResponse)
def order_page(
    order_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    order = db.query(models.PaymentOrder).filter(
        models.PaymentOrder.id == order_id,
        models.PaymentOrder.user_id == user.id,
    ).first()
    if not order:
        raise HTTPException(404)

    return templates.TemplateResponse("billing_order.html", {
        "request": request,
        "user": user,
        "order": order,
        "requisites": FOP_REQUISITES,
        "requisites_ready": requisites_ready(),
        "symbol": CURRENCY_SYMBOL,
    })


@router.post("/billing/order/{order_id}/cancel")
def cancel_order(
    order_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    order = db.query(models.PaymentOrder).filter(
        models.PaymentOrder.id == order_id,
        models.PaymentOrder.user_id == user.id,
    ).first()
    if not order:
        raise HTTPException(404)
    # Оплачене замовлення скасувати не можна — кредити вже нараховані
    if order.status == "pending":
        order.status = "cancelled"
        db.commit()
    return RedirectResponse("/billing", status_code=302)
