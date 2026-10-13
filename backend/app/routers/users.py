from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_company_user, get_current_user, require_permission
from ..models import User
from ..permissions import PERMISSIONS, ROLE_DEFAULT_PERMISSIONS
from ..schemas import PermissionCatalogOut, UserCreate, UserListOut, UserOut, UserUpdate
from ..serializers import user_out
from ..services.users import (
    create_company_user,
    delete_company_user,
    seats_used,
    update_company_user,
)

router = APIRouter(prefix="/api", tags=["users"])

manage_users = require_permission("users.manage")


@router.get("/permissions", response_model=PermissionCatalogOut)
def permission_catalog(_: User = Depends(get_current_user)):
    return PermissionCatalogOut(
        permissions=PERMISSIONS, role_defaults={str(k): v for k, v in ROLE_DEFAULT_PERMISSIONS.items()}
    )


@router.get("/users", response_model=UserListOut)
def list_users(me: User = Depends(manage_users), db: Session = Depends(get_db)):
    users = db.scalars(select(User).where(User.company_id == me.company_id).order_by(User.id)).all()
    return UserListOut(
        users=[user_out(u) for u in users], max_users=me.company.max_users, used=seats_used(db, me.company_id)
    )


def _company_user(db: Session, me: User, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None or user.company_id != me.company_id:
        raise HTTPException(404, "User not found")
    return user


@router.post("/users", response_model=UserOut, status_code=201)
def create_user(body: UserCreate, me: User = Depends(manage_users), db: Session = Depends(get_db)):
    return user_out(create_company_user(db, me.company, body, acting_user=me))


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(user_id: int, body: UserUpdate, me: User = Depends(manage_users), db: Session = Depends(get_db)):
    return user_out(update_company_user(db, _company_user(db, me, user_id), body, me))


@router.delete("/users/{user_id}", status_code=204)
def delete_user(user_id: int, me: User = Depends(manage_users), db: Session = Depends(get_db)):
    delete_company_user(db, _company_user(db, me, user_id), me)


@router.get("/team", response_model=list[UserOut])
def team(me: User = Depends(get_company_user), db: Session = Depends(get_db)):
    """Active colleagues, for assigning tickets and conversations."""
    users = db.scalars(
        select(User).where(User.company_id == me.company_id, User.is_active.is_(True)).order_by(User.full_name)
    ).all()
    return [user_out(u) for u in users]
