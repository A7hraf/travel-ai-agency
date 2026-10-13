"""Answers a company taught its AI: the closest ones are added to the prompt for each reply."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import TrainingExample
from .text import Matcher, keyword_groups

MAX_EXAMPLES_IN_PROMPT = 3


def relevant_examples(db: Session, company_id: int, customer_text: str, previous_text: str = "",
                      limit: int = MAX_EXAMPLES_IN_PROMPT) -> list[TrainingExample]:
    """Examples whose question (and, less, answer) shares words with the customer's message.
    Words of the customer's previous message count half, for follow-ups like "and for kids?"."""
    groups = keyword_groups(customer_text)
    earlier = [g for g in keyword_groups(previous_text) if g not in groups]
    if not groups and not earlier:
        return []
    examples = db.scalars(select(TrainingExample).where(TrainingExample.company_id == company_id)).all()
    scored = []
    for example in examples:
        question, answer = Matcher(example.question), Matcher(example.answer)
        score = sum(2 for g in groups if question.matches(g)) + sum(0.5 for g in groups if answer.matches(g))
        score += sum(1 for g in earlier if question.matches(g))
        if score >= 1:
            scored.append((score, example.id, example))
    scored.sort(key=lambda s: (-s[0], s[1]))
    return [example for _, _, example in scored[:limit]]
