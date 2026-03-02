# api/custom_swagger.py
from fastapi import APIRouter, Response
from pathlib import Path

router = APIRouter()

@router.get("/docs", include_in_schema=False)
def api_docs():
    # Gemeinsame Swagger-HTML-Datei laden
    html_path = Path(__file__).resolve().parent.parent / "static" / "swagger.html"
    html = html_path.read_text(encoding="utf-8")

    # OPENAPI_URL ersetzen
    html = html.replace("{{OPENAPI_URL}}", "/api/openapi.json")

    return Response(content=html, media_type="text/html")
