"""AI training: questions with the company's approved answers. Each company only sees its own."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_permission
from ..models import TrainingExample, User
from ..schemas import TrainingIn, TrainingOut

router = APIRouter(prefix="/api/training", tags=["ai training"])

can_train = require_permission("settings.manage")
MAX_EXAMPLES_PER_COMPANY = 500


def _get(db: Session, me: User, example_id: int) -> TrainingExample:
    example = db.get(TrainingExample, example_id)
    if example is None or example.company_id != me.company_id:
        raise HTTPException(404, "Not found")
    return example


@router.get("", response_model=list[TrainingOut])
def list_examples(me: User = Depends(can_train), db: Session = Depends(get_db)):
    return db.scalars(
        select(TrainingExample).where(TrainingExample.company_id == me.company_id).order_by(TrainingExample.id.desc())
    ).all()


@router.post("", response_model=TrainingOut, status_code=201)
def add_example(body: TrainingIn, me: User = Depends(can_train), db: Session = Depends(get_db)):
    count = db.scalar(select(func.count(TrainingExample.id)).where(TrainingExample.company_id == me.company_id))
    if (count or 0) >= MAX_EXAMPLES_PER_COMPANY:
        raise HTTPException(409, f"Limit of {MAX_EXAMPLES_PER_COMPANY} answers reached")
    example = TrainingExample(company_id=me.company_id, question=body.question.strip(), answer=body.answer.strip())
    db.add(example)
    db.commit()
    db.refresh(example)
    return example


@router.put("/{example_id}", response_model=TrainingOut)
def update_example(example_id: int, body: TrainingIn, me: User = Depends(can_train), db: Session = Depends(get_db)):
    example = _get(db, me, example_id)
    example.question = body.question.strip()
    example.answer = body.answer.strip()
    db.commit()
    db.refresh(example)
    return example


@router.delete("/{example_id}", status_code=204)
def delete_example(example_id: int, me: User = Depends(can_train), db: Session = Depends(get_db)):
    db.delete(_get(db, me, example_id))
    db.commit()
