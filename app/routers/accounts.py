from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..deps import get_current_user

router = APIRouter(prefix="/api/accounts", tags=["accounts"])


@router.get("", response_model=list[schemas.AccountOut])
def list_accounts(user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    return (
        db.query(models.PlatformAccount)
        .filter(models.PlatformAccount.user_id == user.id)
        .order_by(models.PlatformAccount.created_at.desc())
        .all()
    )


@router.delete("/{account_id}")
def disconnect(account_id: int, user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    acc = db.query(models.PlatformAccount).filter(
        models.PlatformAccount.id == account_id,
        models.PlatformAccount.user_id == user.id,
    ).first()
    if not acc:
        raise HTTPException(404, "Akun tidak ditemukan.")
    db.delete(acc)
    db.commit()
    return {"ok": True}
