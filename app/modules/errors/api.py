# app/modules/errors/api.py
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["errors"])

_templates = None


def _get_templates():
    global _templates
    if _templates is None:
        from api.templates import templates as t
        _templates = t
    return _templates


@router.get("", response_class=HTMLResponse)
def get_errors(request: Request):
    from helpers.logger import get_all_errors
    return _get_templates().TemplateResponse(
        "errors/partials/error_list.html",
        {"request": request, "errors": get_all_errors(days=14)},
    )
