from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import LLMAnalysis, Order

router = APIRouter(prefix="/admin", tags=["admin"])
templates = Jinja2Templates(directory="app/templates")


@router.get("", response_class=HTMLResponse)
def admin_home(request: Request, db: Session = Depends(get_db)):
    orders = db.query(Order).order_by(Order.ts.desc()).limit(20).all()
    analyses = db.query(LLMAnalysis).order_by(LLMAnalysis.ts.desc()).limit(20).all()
    return templates.TemplateResponse(
        "admin.html",
        {"request": request, "orders": orders, "analyses": analyses},
    )
