"""AI training: questions with the company's approved answers, the company's knowledge and the
"Try your AI" test chat. Each company only sees its own (the platform owner's console has the same
endpoints under /api/system/companies/{id}/training)."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..ai import training as service
from ..database import get_db
from ..deps import require_permission
from ..models import User
from ..schemas import (
    AIKnowledgeOut,
    AIKnowledgeUpdate,
    TrainingImportIn,
    TrainingImportOut,
    TrainingIn,
    TrainingOut,
    TryAIIn,
    TryAIOut,
)

router = APIRouter(prefix="/api/training", tags=["ai training"])

can_train = require_permission("settings.manage")
MAX_EXAMPLES_PER_COMPANY = service.MAX_EXAMPLES_PER_COMPANY


@router.get("", response_model=list[TrainingOut])
def list_examples(me: User = Depends(can_train), db: Session = Depends(get_db)):
    return service.list_examples(db, me.company_id)


@router.post("", response_model=TrainingOut, status_code=201)
def add_example(body: TrainingIn, me: User = Depends(can_train), db: Session = Depends(get_db)):
    return service.add_example(db, me.company_id, body.question, body.answer)


@router.post("/import", response_model=TrainingImportOut)
def import_examples(body: TrainingImportIn, me: User = Depends(can_train), db: Session = Depends(get_db)):
    return service.import_examples(db, me.company_id, body.text, body.preview)


@router.post("/try", response_model=TryAIOut)
def try_ai(body: TryAIIn, me: User = Depends(can_train), db: Session = Depends(get_db)):
    return service.try_ai(db, me.company, me.id, body.message, [t.model_dump() for t in body.history])


@router.get("/knowledge", response_model=AIKnowledgeOut)
def get_knowledge(me: User = Depends(can_train), db: Session = Depends(get_db)):
    return service.knowledge_out(db, me.company)


@router.patch("/knowledge", response_model=AIKnowledgeOut)
def update_knowledge(body: AIKnowledgeUpdate, me: User = Depends(can_train), db: Session = Depends(get_db)):
    return service.update_knowledge(db, me.company, body.model_dump(exclude_unset=True))


@router.put("/{example_id}", response_model=TrainingOut)
def update_example(example_id: int, body: TrainingIn, me: User = Depends(can_train), db: Session = Depends(get_db)):
    return service.update_example(db, me.company_id, example_id, body.question, body.answer)


@router.delete("/{example_id}", status_code=204)
def delete_example(example_id: int, me: User = Depends(can_train), db: Session = Depends(get_db)):
    service.delete_example(db, me.company_id, example_id)
