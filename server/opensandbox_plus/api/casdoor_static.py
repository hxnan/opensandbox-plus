from __future__ import annotations

import re
from importlib import resources

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, Response

router = APIRouter()


def _brand_logo() -> str:
    try:
        return (
            resources.files("opensandbox_plus")
            .joinpath("static/brand/opensandbox-plus-logo.svg")
            .read_text(encoding="utf-8")
        )
    except FileNotFoundError:
        return """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 420 96" role="img">
  <rect width="420" height="96" fill="white"/>
  <text x="24" y="60" font-family="Segoe UI, Arial, sans-serif" font-size="34" font-weight="700" fill="#031426">OpenSandbox</text>
  <text x="276" y="60" font-family="Segoe UI, Arial, sans-serif" font-size="34" font-weight="700" fill="#0b63f5">Plus</text>
</svg>"""


def _svg_response(svg: str) -> Response:
    return Response(
        content=svg,
        media_type="image/svg+xml",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@router.get("/casdoor-static/logo.svg", include_in_schema=False)
async def casdoor_logo() -> Response:
    return _svg_response(_brand_logo())


@router.get("/casdoor-static/img/casbin/favicon.ico", include_in_schema=False)
@router.get("/casdoor-static/favicon.ico", include_in_schema=False)
async def casdoor_favicon() -> Response:
    svg = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
  <rect width="64" height="64" rx="14" fill="#eef6ff"/>
  <path d="M19 40h-3c-5 0-9-4-9-9s4-9 9-9c1-7 7-12 15-12s14 5 16 12c6 0 10 4 10 10s-4 8-9 8h-4" fill="none" stroke="#0b63e5" stroke-width="4" stroke-linecap="round"/>
  <path d="M32 22l10 6v12l-10 6-10-6V28z" fill="#0d6bfa"/>
  <circle cx="22" cy="48" r="3" fill="#087f82"/><circle cx="32" cy="48" r="3" fill="#087f82"/><circle cx="42" cy="48" r="3" fill="#087f82"/>
</svg>"""
    return _svg_response(svg)


@router.get("/casdoor-static/site/casdoor/manifest.json", include_in_schema=False)
async def casdoor_manifest() -> JSONResponse:
    return JSONResponse(
        {
            "name": "OpenSandbox Plus Console",
            "short_name": "OpenSandbox Plus",
            "icons": [
                {
                    "src": "/casdoor-static/img/casbin/favicon.ico",
                    "sizes": "64x64",
                    "type": "image/svg+xml",
                }
            ],
            "start_url": "/",
            "display": "standalone",
            "background_color": "#ffffff",
            "theme_color": "#0b63e5",
        },
        headers={"Cache-Control": "public, max-age=86400"},
    )


@router.get("/casdoor-static/flag-icons/{country_code}.svg", include_in_schema=False)
async def casdoor_flag_icon(country_code: str) -> Response:
    code = country_code.removesuffix(".svg").upper()
    if not re.fullmatch(r"[A-Z]{2,3}", code):
        raise HTTPException(status_code=404, detail="flag icon not found")
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 36 24" role="img" aria-label="{code}">
  <rect width="36" height="24" rx="3" fill="#eef6ff"/>
  <rect y="16" width="36" height="8" rx="3" fill="#0b63e5"/>
  <text x="18" y="14" text-anchor="middle" font-family="Segoe UI, Arial, sans-serif" font-size="9" font-weight="700" fill="#031426">{code}</text>
</svg>"""
    return _svg_response(svg)
