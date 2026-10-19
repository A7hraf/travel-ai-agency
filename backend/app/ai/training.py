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


# --- Bulk import ("question | answer" lines or CSV) -------------------------------------

MAX_EXAMPLES_PER_COMPANY = 500
MAX_IMPORT_ROWS = 200
MAX_IMPORT_CHARS = 200_000
QUESTION_LIMITS = (2, 1000)
ANSWER_LIMITS = (1, 4000)
_HEADER_WORDS = {"question", "questions", "q", "سؤال", "السؤال", "الأسئلة"}


def _split_line(line: str) -> list[str] | None:
    for sep in ("|", "\t"):
        if sep in line:
            question, answer = line.split(sep, 1)
            return [question, answer]
    return None


def parse_import(text: str) -> tuple[list[tuple[int, str, str]], list[dict]]:
    """Rows (line number, question, answer) and problems ({"line", "error"}) of pasted text.

    Each line is "question | answer" (or question<TAB>answer, as copied from a spreadsheet);
    text without | or tabs is read as CSV with two columns (quotes allowed for commas and new lines).
    A first row "question, answer" is skipped.
    """
    import csv
    import io

    text = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")
    rows: list[tuple[int, list[str]]] = []
    if any(_split_line(line) for line in lines):
        for n, line in enumerate(lines, 1):
            if line.strip():
                rows.append((n, _split_line(line) or [line]))
    else:
        reader = csv.reader(io.StringIO(text))
        for record in reader:
            if any(c.strip() for c in record):
                rows.append((reader.line_num, record))

    out: list[tuple[int, str, str]] = []
    problems: list[dict] = []
    for i, (n, cells) in enumerate(rows):
        cells = [c.strip().strip('"').strip() for c in cells]
        if i == 0 and cells and cells[0].lower() in _HEADER_WORDS:
            continue
        if len(cells) < 2 or not cells[0] or not cells[1]:
            problems.append({"line": n, "error": "Needs a question and an answer separated by |"})
            continue
        question, answer = cells[0], ",".join(cells[1:]).strip() if len(cells) > 2 else cells[1]
        if not QUESTION_LIMITS[0] <= len(question) <= QUESTION_LIMITS[1]:
            problems.append({"line": n, "error": "The question must have 2 to 1000 characters"})
            continue
        if len(answer) > ANSWER_LIMITS[1]:
            problems.append({"line": n, "error": "The answer can have at most 4000 characters"})
            continue
        out.append((n, question, answer))
    return out, problems


def import_examples(db: Session, company_id: int, text: str, preview: bool = False) -> dict:
    """Adds the valid rows of pasted text (see parse_import); duplicates of existing questions are skipped.
    With ``preview`` nothing is saved: the caller shows what would be added."""
    from fastapi import HTTPException
    from sqlalchemy import func

    if len(text or "") > MAX_IMPORT_CHARS:
        raise HTTPException(413, "The text is too long. Import at most 200 answers at a time.")
    rows, problems = parse_import(text)
    if not rows and not problems:
        raise HTTPException(400, "Paste at least one line: question | answer")
    if len(rows) > MAX_IMPORT_ROWS:
        raise HTTPException(400, "Import at most 200 answers at a time.")

    existing = {q.strip().lower() for q in db.scalars(
        select(TrainingExample.question).where(TrainingExample.company_id == company_id))}
    count = db.scalar(select(func.count(TrainingExample.id)).where(TrainingExample.company_id == company_id)) or 0
    room = MAX_EXAMPLES_PER_COMPANY - count

    to_add: list[dict] = []
    duplicates: list[dict] = []
    seen = set(existing)
    for n, question, answer in rows:
        key = question.lower()
        if key in seen:
            duplicates.append({"line": n, "question": question})
            continue
        seen.add(key)
        to_add.append({"line": n, "question": question, "answer": answer})
    if len(to_add) > room:
        raise HTTPException(409, f"Limit of {MAX_EXAMPLES_PER_COMPANY} answers reached")
    if not preview:
        for row in to_add:
            db.add(TrainingExample(company_id=company_id, question=row["question"], answer=row["answer"]))
        db.commit()
    return {"added": 0 if preview else len(to_add), "rows": to_add, "duplicates": duplicates,
            "problems": problems, "preview": preview}


# --- Shared by the company's training page and the platform owner's console -------------


def get_example(db: Session, company_id: int, example_id: int) -> TrainingExample:
    from fastapi import HTTPException

    example = db.get(TrainingExample, example_id)
    if example is None or example.company_id != company_id:
        raise HTTPException(404, "Not found")
    return example


def list_examples(db: Session, company_id: int) -> list[TrainingExample]:
    return list(db.scalars(
        select(TrainingExample).where(TrainingExample.company_id == company_id).order_by(TrainingExample.id.desc())
    ).all())


def add_example(db: Session, company_id: int, question: str, answer: str) -> TrainingExample:
    from fastapi import HTTPException
    from sqlalchemy import func

    count = db.scalar(select(func.count(TrainingExample.id)).where(TrainingExample.company_id == company_id))
    if (count or 0) >= MAX_EXAMPLES_PER_COMPANY:
        raise HTTPException(409, f"Limit of {MAX_EXAMPLES_PER_COMPANY} answers reached")
    example = TrainingExample(company_id=company_id, question=question.strip(), answer=answer.strip())
    db.add(example)
    db.commit()
    db.refresh(example)
    return example


def update_example(db: Session, company_id: int, example_id: int, question: str, answer: str) -> TrainingExample:
    example = get_example(db, company_id, example_id)
    example.question = question.strip()
    example.answer = answer.strip()
    db.commit()
    db.refresh(example)
    return example


def delete_example(db: Session, company_id: int, example_id: int) -> None:
    db.delete(get_example(db, company_id, example_id))
    db.commit()


KNOWLEDGE_FIELDS = ("ai_agent_name", "ai_welcome_message", "ai_welcome_message_ar", "ai_instructions",
                    "knowledge_base")


def knowledge_out(db: Session, company) -> dict:
    from sqlalchemy import func

    return {
        "ai_agent_name": company.ai_agent_name,
        "ai_welcome_message": company.ai_welcome_message,
        "ai_welcome_message_ar": company.ai_welcome_message_ar,
        "ai_instructions": company.ai_instructions or "",
        "knowledge_base": company.knowledge_base or "",
        "examples": db.scalar(select(func.count(TrainingExample.id))
                              .where(TrainingExample.company_id == company.id)) or 0,
    }


def update_knowledge(db: Session, company, data: dict) -> dict:
    """The AI's name, welcome messages, instructions and knowledge (same rules as the settings page:
    the agent name can't be blanked, the texts can be emptied)."""
    for key in KNOWLEDGE_FIELDS:
        if key not in data:
            continue
        value = data[key]
        if key == "ai_agent_name":
            value = (value or "").strip()
            if not value:
                continue
        elif key in ("ai_instructions", "knowledge_base"):
            value = value or ""
        else:
            value = (value or "").strip() or None
        setattr(company, key, value)
    db.commit()
    return knowledge_out(db, company)


TRY_LIMIT_PER_MINUTE = 20


def try_ai(db: Session, company, user_id: int, message: str, history: list[dict]) -> dict:
    """One answer of the test chat (rate-limited per person). Nothing is saved."""
    from ..ratelimit import limiter
    from .agent import run_sandbox

    limiter.check(f"try-ai:{user_id}", TRY_LIMIT_PER_MINUTE, "Please wait a minute before testing again")
    try:
        return run_sandbox(db, company, message.strip(), history)
    finally:
        db.rollback()  # belt and braces: the test chat never writes anything
