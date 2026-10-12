"""Image uploads (logos, package photos, page banners), stored in the database.

Only JPEG, PNG and WebP are accepted, checked by their real content (not the file name), and
served with headers that stop a browser from running anything inside them.
"""

import base64
import binascii

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_company_user, require_system_admin
from ..models import Company, MediaFile, User
from ..permissions import effective_permissions
from ..security import random_token

router = APIRouter(tags=["media"])

MAX_BYTES = 2_500_000
MAX_FILES_PER_COMPANY = 300
MAX_TOTAL_BYTES_PER_COMPANY = 100_000_000

SIGNATURES = {
    "image/jpeg": lambda d: d[:3] == b"\xff\xd8\xff",
    "image/png": lambda d: d[:8] == b"\x89PNG\r\n\x1a\n",
    "image/webp": lambda d: d[:4] == b"RIFF" and d[8:12] == b"WEBP",
}


class UploadIn(BaseModel):
    content_type: str = Field(max_length=30)
    data_base64: str = Field(max_length=MAX_BYTES * 4 // 3 + 16)


class UploadOut(BaseModel):
    url: str
    size: int


def store_image(db: Session, company: Company, body: UploadIn) -> UploadOut:
    check = SIGNATURES.get(body.content_type)
    if check is None:
        raise HTTPException(415, "Only JPEG, PNG or WebP images are allowed")
    try:
        data = base64.b64decode(body.data_base64, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(400, "The image data is not valid")
    if not data or len(data) > MAX_BYTES:
        raise HTTPException(413, "The image is too large (maximum 2.5 MB)")
    if not check(data):
        raise HTTPException(415, "The file is not a real JPEG, PNG or WebP image")
    count, total = db.execute(
        select(func.count(MediaFile.id), func.coalesce(func.sum(MediaFile.size), 0)).where(
            MediaFile.company_id == company.id
        )
    ).one()
    if count >= MAX_FILES_PER_COMPANY or total + len(data) > MAX_TOTAL_BYTES_PER_COMPANY:
        raise HTTPException(409, "Image storage limit reached for this company")
    media = MediaFile(company_id=company.id, key=random_token(24), content_type=body.content_type,
                      size=len(data), data=data)
    db.add(media)
    db.commit()
    return UploadOut(url=f"/api/media/{media.key}", size=media.size)


def media_belongs_to(db: Session, url: str | None, company_id: int) -> bool:
    if not url or not url.startswith("/api/media/"):
        return True
    key = url.removeprefix("/api/media/")
    owner = db.scalar(select(MediaFile.company_id).where(MediaFile.key == key))
    return owner == company_id


@router.post("/api/media", response_model=UploadOut, status_code=201)
def upload(body: UploadIn, me: User = Depends(get_company_user), db: Session = Depends(get_db)):
    perms = effective_permissions(me)
    if "packages.manage" not in perms and "settings.manage" not in perms:
        raise HTTPException(403, "Missing permission: packages.manage or settings.manage")
    return store_image(db, me.company, body)


@router.post("/api/system/companies/{company_id}/media", response_model=UploadOut, status_code=201)
def upload_for_company(company_id: int, body: UploadIn, _: User = Depends(require_system_admin),
                       db: Session = Depends(get_db)):
    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(404, "Company not found")
    return store_image(db, company, body)


@router.get("/api/media/{key}")
def serve(key: str, db: Session = Depends(get_db)):
    media = db.scalar(select(MediaFile).where(MediaFile.key == key))
    if media is None:
        raise HTTPException(404, "Not found")
    return Response(
        content=media.data,
        media_type=media.content_type,
        headers={
            "Cache-Control": "public, max-age=31536000, immutable",
            "Content-Security-Policy": "default-src 'none'; sandbox",
            "Content-Disposition": "inline",
        },
    )
