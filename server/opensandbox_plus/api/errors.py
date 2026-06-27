from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field


class ErrorDetail(BaseModel):
    code: str = Field(examples=["UNAUTHENTICATED"])
    message: str = Field(examples=["missing Authorization header"])
    request_id: str | None = Field(default=None, examples=["req_01HTZ8K4Y2Q7F2N"])
    details: Any | None = None


class ErrorResponse(BaseModel):
    detail: ErrorDetail


COMMON_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    400: {"model": ErrorResponse, "description": "Invalid request"},
    401: {"model": ErrorResponse, "description": "Authentication failed"},
    403: {"model": ErrorResponse, "description": "Permission denied"},
    404: {"model": ErrorResponse, "description": "Resource not found"},
    409: {"model": ErrorResponse, "description": "Conflict"},
    413: {"model": ErrorResponse, "description": "Payload too large"},
    422: {"model": ErrorResponse, "description": "Validation error"},
    429: {"model": ErrorResponse, "description": "Quota or rate limit exceeded"},
    500: {"model": ErrorResponse, "description": "Internal server error"},
    502: {"model": ErrorResponse, "description": "OpenSandbox backend error"},
}

ERROR_CODE_CATALOG: dict[str, str] = {
    "UNAUTHENTICATED": "Missing, malformed, expired, or invalid management-plane bearer token.",
    "FORBIDDEN": "Authenticated user does not have the required role or active status.",
    "MISSING_API_KEY": "OpenSandbox-compatible API call is missing OPEN-SANDBOX-API-KEY.",
    "INVALID_CREDENTIAL": "Cloud sandbox credential is invalid, disabled, expired, or malformed.",
    "INVALID_REQUEST": "Request body, query, or upload payload is invalid.",
    "VALIDATION_ERROR": "Request failed schema validation.",
    "NOT_FOUND": "Requested resource does not exist.",
    "CONFLICT": "Requested mutation conflicts with existing state.",
    "QUOTA_EXCEEDED": "User, credential, or platform quota was exceeded.",
    "PAYLOAD_TOO_LARGE": "Upload or request payload exceeds configured size limits.",
    "OPENSANDBOX_BACKEND_ERROR": "The selected OpenSandbox backend is unavailable or returned an error.",
    "NOT_IMPLEMENTED": "The requested compatibility surface is reserved but not implemented.",
}


def configure_error_contract(app: FastAPI) -> None:
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.openapi = lambda: openapi_with_error_contract(app)  # type: ignore[method-assign]


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        headers=exc.headers,
        content={"detail": _normalize_error_detail(request, exc.detail, exc.status_code)},
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "detail": _normalize_error_detail(
                request,
                {
                    "code": "VALIDATION_ERROR",
                    "message": "request validation failed",
                    "details": exc.errors(),
                },
                status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        },
    )


def openapi_with_error_contract(app: FastAPI) -> dict[str, Any]:
    if app.openapi_schema:
        return app.openapi_schema

    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    components = schema.setdefault("components", {}).setdefault("schemas", {})
    error_response_schema = ErrorResponse.model_json_schema(ref_template="#/components/schemas/{model}")
    error_response_schema.pop("$defs", None)
    components.setdefault("ErrorDetail", ErrorDetail.model_json_schema(ref_template="#/components/schemas/{model}"))
    components.setdefault("ErrorResponse", error_response_schema)
    _attach_common_error_responses(schema)
    app.openapi_schema = schema
    return app.openapi_schema


def _attach_common_error_responses(schema: dict[str, Any]) -> None:
    for path_item in schema.get("paths", {}).values():
        if not isinstance(path_item, dict):
            continue
        for operation in path_item.values():
            if not isinstance(operation, dict):
                continue
            responses = operation.setdefault("responses", {})
            for status_code, response_spec in COMMON_ERROR_RESPONSES.items():
                responses.setdefault(
                    str(status_code),
                    {
                        "description": str(response_spec["description"]),
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/ErrorResponse"},
                            }
                        },
                    },
                )


def _normalize_error_detail(request: Request, detail: Any, status_code: int) -> dict[str, Any]:
    request_id = getattr(request.state, "request_id", None)
    if isinstance(detail, dict):
        code = str(detail.get("code") or _default_error_code(status_code))
        message = str(detail.get("message") or _default_error_message(status_code))
        normalized: dict[str, Any] = {
            "code": code,
            "message": message,
            "request_id": request_id,
        }
        if "details" in detail:
            normalized["details"] = detail["details"]
        return normalized

    return {
        "code": _default_error_code(status_code),
        "message": str(detail or _default_error_message(status_code)),
        "request_id": request_id,
    }


def _default_error_code(status_code: int) -> str:
    if status_code == 401:
        return "UNAUTHENTICATED"
    if status_code == 403:
        return "FORBIDDEN"
    if status_code == 404:
        return "NOT_FOUND"
    if status_code == 409:
        return "CONFLICT"
    if status_code == 413:
        return "PAYLOAD_TOO_LARGE"
    if status_code == 422:
        return "VALIDATION_ERROR"
    if status_code == 429:
        return "QUOTA_EXCEEDED"
    if status_code == 502:
        return "OPENSANDBOX_BACKEND_ERROR"
    if status_code >= 500:
        return "INTERNAL_ERROR"
    return "INVALID_REQUEST"


def _default_error_message(status_code: int) -> str:
    if status_code >= 500:
        return "internal server error"
    return "request failed"
