"""Answers a company taught its AI: the closest ones are added to the prompt for each reply."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import TrainingExample
from .text import keywords

MAX_EXAMPLES_IN_PROMPT = 3


def relevant_examples(db: Session, company_id: int, customer_text: str,
                      limit: int = MAX_EXAMPLES_IN_PROMPT) -> list[TrainingExample]:
    wanted = set(keywords(customer_text))
    if not wanted:
        return []
    examples = db.scalars(select(TrainingExample).where(TrainingExample.company_id == company_id)).all()
    scored = []
    for example in examples:
        score = len(wanted & set(keywords(example.question)))
        if score:
            scored.append((score, example.id, example))
    scored.sort(key=lambda s: (-s[0], s[1]))
    return [example for _, _, example in scored[:limit]]
