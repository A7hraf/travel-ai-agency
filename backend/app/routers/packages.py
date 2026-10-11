from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_permission
from ..models import Ticket, TravelPackage, User
from ..schemas import PackageIn, PackageOut

router = APIRouter(prefix="/api/packages", tags=["packages"])


def _apply(pkg: TravelPackage, body: PackageIn, default_currency: str) -> None:
    data = body.model_dump()
    data["currency"] = (data.get("currency") or default_currency).upper()
    data["departure_dates"] = sorted({d.isoformat() for d in body.departure_dates})
    data["includes"] = [s.strip() for s in body.includes if s.strip()]
    data["excludes"] = [s.strip() for s in body.excludes if s.strip()]
    data["tags"] = [s.strip().lower() for s in body.tags if s.strip()]
    for key, value in data.items():
        setattr(pkg, key, value)


def _get(db: Session, me: User, package_id: int) -> TravelPackage:
    pkg = db.get(TravelPackage, package_id)
    if pkg is None or pkg.company_id != me.company_id:
        raise HTTPException(404, "Package not found")
    return pkg


@router.get("", response_model=list[PackageOut])
def list_packages(me: User = Depends(require_permission("packages.view")), db: Session = Depends(get_db)):
    return db.scalars(
        select(TravelPackage).where(TravelPackage.company_id == me.company_id).order_by(TravelPackage.id.desc())
    ).all()


@router.get("/{package_id}", response_model=PackageOut)
def get_package(package_id: int, me: User = Depends(require_permission("packages.view")),
                db: Session = Depends(get_db)):
    return _get(db, me, package_id)


@router.post("", response_model=PackageOut, status_code=201)
def create_package(body: PackageIn, me: User = Depends(require_permission("packages.manage")),
                   db: Session = Depends(get_db)):
    pkg = TravelPackage(company_id=me.company_id)
    _apply(pkg, body, me.company.currency)
    db.add(pkg)
    db.commit()
    db.refresh(pkg)
    return pkg


@router.put("/{package_id}", response_model=PackageOut)
def update_package(package_id: int, body: PackageIn, me: User = Depends(require_permission("packages.manage")),
                   db: Session = Depends(get_db)):
    pkg = _get(db, me, package_id)
    _apply(pkg, body, me.company.currency)
    db.commit()
    db.refresh(pkg)
    return pkg


@router.delete("/{package_id}", status_code=204)
def delete_package(package_id: int, me: User = Depends(require_permission("packages.manage")),
                   db: Session = Depends(get_db)):
    pkg = _get(db, me, package_id)
    if db.scalar(select(Ticket.id).where(Ticket.package_id == pkg.id).limit(1)):
        # Keep the history of booked packages; hide it from customers instead.
        pkg.is_active = False
    else:
        db.delete(pkg)
    db.commit()
