import io
from datetime import datetime

import qrcode
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse, StreamingResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from .database import get_db
from .models import ScanEvent, UrlMapping
from .schemas import (
    AnalyticsResponse,
    CreateRequest,
    CreateResponse,
    QRInfoResponse,
    UpdateRequest,
)
from .token_gen import generate_token
from .url_validator import validate_url


router = APIRouter()
redirect_cache: dict[str, tuple[str, datetime | None]] = {}


def _base_url(request: Request) -> str:
    return str(request.base_url).rstrip("/")


def _short_url(request: Request, token: str) -> str:
    return f"{_base_url(request)}/r/{token}"


def _qr_code_url(request: Request, token: str) -> str:
    return f"{_base_url(request)}/api/qr/{token}/image"


def _is_expired(mapping: UrlMapping) -> bool:
    return mapping.expires_at is not None and mapping.expires_at <= datetime.utcnow()


def _to_info_response(mapping: UrlMapping, request: Request) -> QRInfoResponse:
    return QRInfoResponse(
        token=mapping.token,
        original_url=mapping.original_url,
        short_url=_short_url(request, mapping.token),
        qr_code_url=_qr_code_url(request, mapping.token),
        created_at=mapping.created_at,
        updated_at=mapping.updated_at,
        expires_at=mapping.expires_at,
        is_deleted=mapping.is_deleted,
    )


def _get_mapping(token: str, db: Session) -> UrlMapping:
    mapping = db.query(UrlMapping).filter(UrlMapping.token == token).first()
    if mapping is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Token not found")
    return mapping


def _get_active_mapping(token: str, db: Session) -> UrlMapping:
    mapping = _get_mapping(token, db)
    if mapping.is_deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Token deleted")
    return mapping


def _record_scan(token: str, request: Request, db: Session) -> None:
    db.add(
        ScanEvent(
            token=token,
            user_agent=request.headers.get("user-agent"),
            ip_address=request.client.host if request.client else None,
        )
    )
    db.commit()


@router.post("/api/qr/create", response_model=CreateResponse)
def create_qr(req: CreateRequest, request: Request, db: Session = Depends(get_db)):
    try:
        original_url = validate_url(req.url)
        token = generate_token(db)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    mapping = UrlMapping(token=token, original_url=original_url, expires_at=req.expires_at)
    db.add(mapping)
    db.commit()
    db.refresh(mapping)

    if not _is_expired(mapping):
        redirect_cache[token] = (original_url, mapping.expires_at)

    return CreateResponse(
        token=token,
        short_url=_short_url(request, token),
        qr_code_url=_qr_code_url(request, token),
        original_url=original_url,
    )


@router.get("/r/{token}")
def redirect(token: str, request: Request, db: Session = Depends(get_db)):
    cached = redirect_cache.get(token)
    if cached is not None:
        cached_url, expires_at = cached
        if expires_at is not None and expires_at <= datetime.utcnow():
            redirect_cache.pop(token, None)
            raise HTTPException(status_code=status.HTTP_410_GONE, detail="Token expired")
        _record_scan(token, request, db)
        return RedirectResponse(cached_url, status_code=status.HTTP_302_FOUND)

    mapping = _get_mapping(token, db)
    if mapping.is_deleted:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Token deleted")
    if _is_expired(mapping):
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Token expired")

    redirect_cache[token] = (mapping.original_url, mapping.expires_at)
    _record_scan(token, request, db)
    return RedirectResponse(mapping.original_url, status_code=status.HTTP_302_FOUND)


@router.get("/api/qr/{token}", response_model=QRInfoResponse)
def get_qr_info(token: str, request: Request, db: Session = Depends(get_db)):
    mapping = _get_active_mapping(token, db)
    return _to_info_response(mapping, request)


@router.patch("/api/qr/{token}", response_model=QRInfoResponse)
def update_qr(token: str, req: UpdateRequest, request: Request, db: Session = Depends(get_db)):
    mapping = _get_active_mapping(token, db)

    if "url" in req.model_fields_set:
        try:
            mapping.original_url = validate_url(req.url or "")
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    if "expires_at" in req.model_fields_set:
        mapping.expires_at = req.expires_at

    redirect_cache.pop(token, None)
    db.commit()
    db.refresh(mapping)

    if not mapping.is_deleted and not _is_expired(mapping):
        redirect_cache[token] = (mapping.original_url, mapping.expires_at)

    return _to_info_response(mapping, request)


@router.delete("/api/qr/{token}")
def delete_qr(token: str, db: Session = Depends(get_db)):
    mapping = _get_active_mapping(token, db)
    mapping.is_deleted = True
    redirect_cache.pop(token, None)
    db.commit()
    return {"detail": "Deleted"}


@router.get("/api/qr/{token}/image")
def get_qr_image(token: str, request: Request, db: Session = Depends(get_db)):
    mapping = _get_active_mapping(token, db)
    if _is_expired(mapping):
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Token expired")

    img = qrcode.make(_short_url(request, token))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return StreamingResponse(buf, media_type="image/png")


@router.get("/api/qr/{token}/analytics", response_model=AnalyticsResponse)
def get_analytics(token: str, db: Session = Depends(get_db)):
    _get_active_mapping(token, db)

    total = db.query(func.count(ScanEvent.id)).filter(ScanEvent.token == token).scalar() or 0
    daily = (
        db.query(
            func.date(ScanEvent.scanned_at).label("date"),
            func.count(ScanEvent.id).label("count"),
        )
        .filter(ScanEvent.token == token)
        .group_by(func.date(ScanEvent.scanned_at))
        .order_by(func.date(ScanEvent.scanned_at))
        .all()
    )

    return AnalyticsResponse(
        token=token,
        total_scans=total,
        scans_by_day=[{"date": str(row.date), "count": row.count} for row in daily],
    )
