"""Keyword matching that works for English and Arabic (used by package search and training lookup)."""

import re

_STOPWORDS = {
    # English
    "the", "and", "for", "with", "trip", "trips", "travel", "package", "packages", "want", "would",
    "like", "looking", "need", "please", "some", "any", "can", "you", "show", "offer", "offers",
    "holiday", "vacation", "tour", "tours", "about", "what", "have", "there", "from", "days", "day",
    "night", "nights", "person", "people", "our", "this", "that", "next", "month", "year", "how",
    "much", "does", "are", "your", "who", "when", "where", "which", "will",
    # Arabic (after normalisation)
    "في", "من", "علي", "الي", "عن", "هل", "ما", "ماذا", "كم", "اريد", "ابغي", "ابي", "نبي", "نبغي",
    "رحله", "رحلات", "سفر", "عرض", "عروض", "باقه", "باقات", "لو", "ممكن", "عندكم", "هذا", "هذه", "مع",
    "انا", "نحن", "كيف", "متي", "اين", "وين", "شو", "ايش", "يوم", "ايام", "ليله", "ليالي", "شخص",
}

_ARABIC_PREFIXES = ("وال", "بال", "كال", "فال", "لل", "ال")


def normalize(text: str) -> str:
    """Lower-case, and unify Arabic letter variants so 'التأشيرة' matches 'تاشيره'."""
    text = (text or "").lower()
    text = re.sub("[ً-ٰٟـ]", "", text)  # harakat and tatweel
    text = re.sub("[أإآٱ]", "ا", text)
    return text.replace("ة", "ه").replace("ى", "ي").replace("ؤ", "و").replace("ئ", "ي")


def _strip_arabic_prefix(word: str) -> str:
    for prefix in _ARABIC_PREFIXES:
        if word.startswith(prefix) and len(word) - len(prefix) >= 3:
            return word[len(prefix):]
    return word


def keywords(text: str) -> list[str]:
    words = re.findall(r"\w+", normalize(text))
    out = []
    for w in words:
        w = _strip_arabic_prefix(w)
        if len(w) >= 3 and w not in _STOPWORDS and not w.isdigit():
            out.append(w)
    return out
