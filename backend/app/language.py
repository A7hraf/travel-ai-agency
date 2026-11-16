"""The language of a conversation: the AI and every update the client gets use it.

It follows what the client writes (Arabic or English), unless the client asked for one language ("reply in
English", "كلمني بالعربي"): then it stays until they ask for the other.
"""

from __future__ import annotations

import re
from typing import NamedTuple

LANGS = ("en", "ar")
_ARABIC = re.compile(r"[؀-ۿݐ-ݿ]")
_LATIN = re.compile(r"[A-Za-z]")
_ASK = {
    "en": re.compile(r"\b(?:in|speak|reply|write|answer|talk|use)\s+(?:in\s+)?english\b|\benglish\s+please\b|"
                     r"بالانجليزي|بالإنجليزي|بالانجليزية|بالإنجليزية|انجليزي\s+لو\s+سمحت", re.I),
    "ar": re.compile(r"\b(?:in|speak|reply|write|answer|talk|use)\s+(?:in\s+)?arabic\b|\barabic\s+please\b|"
                     r"بالعربي|بالعربية|عربي\s+لو\s+سمحت", re.I),
}


class Bi(NamedTuple):
    """A message to a client in both languages; the conversation's language picks one."""

    en: str
    ar: str


def detect(text: str) -> str | None:
    """The language a message is written in, when it is clear."""
    ar, latin = len(_ARABIC.findall(text or "")), len(_LATIN.findall(text or ""))
    if ar >= 3 and ar >= latin:
        return "ar"
    if latin >= 3 and latin > ar * 2:
        return "en"
    return None


def asked_for(text: str) -> str | None:
    """The language the client asked us to use, if they asked."""
    found = [lang for lang, pattern in _ASK.items() if pattern.search(text or "")]
    return found[0] if len(found) == 1 else None


def follow(conversation, text: str) -> None:
    """Updates the conversation's language from the client's new message."""
    wanted = asked_for(text)
    if wanted:
        conversation.language, conversation.language_fixed = wanted, True
        return
    seen = detect(text)
    if seen and not conversation.language_fixed:
        conversation.language = seen


def pick(text: str | Bi, lang: str | None) -> str:
    if isinstance(text, Bi):
        if lang == "ar":
            return text.ar
        if lang == "en":
            return text.en
        return f"{text.en}\n{text.ar}"
    return text


NAMES = {"en": "English", "ar": "Arabic (friendly Gulf/Omani Arabic)"}


def prompt_rule(conversation) -> str:
    lang = getattr(conversation, "language", None)
    if lang in NAMES and getattr(conversation, "language_fixed", False):
        return f"The customer asked for replies in {NAMES[lang]}: always reply in {NAMES[lang]} until they ask otherwise."
    if lang in NAMES:
        return (f"The customer writes in {NAMES[lang]}: reply in {NAMES[lang]}. If they switch language or ask for "
                "another one, follow them.")
    return "Reply in the customer's language (Arabic: friendly Gulf/Omani Arabic)."
