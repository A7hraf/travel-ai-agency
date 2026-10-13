"""Keyword matching that works for English and Arabic (used by package search and training lookup).

A query becomes a list of *groups*: each group is one word of the customer with its
alternatives (Arabic prefix and ending variants, synonyms in both languages). A group
matches a text when any alternative does. English words match whole words (or the start
of a word for long words), so "sea" does not match "season"; Arabic words match inside
words because Arabic glues prefixes to words; one typo is forgiven in long words.
"""

import re

_STOPWORDS = {
    # English
    "the", "and", "for", "with", "trip", "trips", "travel", "package", "packages", "want", "would",
    "like", "looking", "need", "please", "some", "any", "can", "you", "show", "offer", "offers",
    "holiday", "vacation", "tour", "tours", "about", "what", "have", "there", "from", "days", "day",
    "night", "nights", "person", "people", "our", "this", "that", "next", "month", "months", "year", "how",
    "much", "does", "are", "your", "who", "when", "where", "which", "will", "week", "weeks", "price",
    "prices", "cost", "january", "february", "march", "april", "june", "july", "august",
    "september", "october", "november", "december", "book", "booking", "go", "going", "visit",
    # Arabic (after normalisation and prefix stripping)
    "في", "من", "علي", "الي", "عن", "هل", "ما", "ماذا", "كم", "اريد", "ابغي", "ابي", "نبي", "نبغي",
    "رحله", "رحلات", "سفر", "عرض", "عروض", "باقه", "باقات", "لو", "ممكن", "عندكم", "هذا", "هذه", "مع",
    "انا", "نحن", "كيف", "متي", "اين", "وين", "شو", "ايش", "يوم", "ايام", "ليله", "ليالي", "شخص",
    "شهر", "اشهر", "جاي", "قادم", "قادمه", "جايه", "اسبوع", "سنه", "نسافر", "اسافر", "سافر", "بغيت",
    "يناير", "فبراير", "مارس", "ابريل", "مايو", "يونيو", "يوليو", "اغسطس", "سبتمبر", "اكتوبر",
    "نوفمبر", "ديسمبر", "سعر", "اسعار", "حجز", "احجز", "تكلفه", "عندك", "عطيني", "ابغا",
}

_ARABIC_PREFIXES = ("وال", "بال", "كال", "فال", "لل", "ال")
_ARABIC_LETTER_PREFIXES = ("و", "ل", "ب", "ف", "ك")
_ARABIC_SUFFIXES = ("يات", "يه", "ات", "ين", "ون", "ه", "ي")

# Words customers use for the same thing, in English and Arabic (normalised forms).
_SYNONYMS = [
    {"family", "families", "kids", "kid", "children", "child", "عايليه", "عاييله", "عاييلي", "عايله", "اطفال",
     "طفل", "اولاد", "عيال", "عاييلات"},
    {"beach", "beaches", "sea", "island", "islands", "شاطي", "شواطي", "بحر", "جزيره", "جزر"},
    {"honeymoon", "honeymooners", "عسل", "عرسان", "عروسين"},
    {"umrah", "umra", "omra", "omrah", "عمره", "mecca", "makkah", "مكه"},
    {"turkey", "turkiye", "türkiye", "istanbul", "تركيا", "اسطنبول"},
    {"uae", "emirates", "dubai", "امارات", "دبي"},
    {"salalah", "dhofar", "khareef", "صلاله", "ظفار", "خريف"},
    {"maldives", "مالديف"},
    {"georgia", "tbilisi", "جورجيا", "تبليسي"},
    {"egypt", "cairo", "مصر", "قاهره"},
    {"europe", "اوروبا"},
    {"saudi", "السعوديه", "سعوديه"},
]
_SYNONYM_OF: dict[str, set[str]] = {}
for _group in _SYNONYMS:
    for _word in _group:
        _SYNONYM_OF[_word] = _group


def normalize(text: str) -> str:
    """Lower-case, and unify Arabic letter variants so 'التأشيرة' matches 'تاشيره'."""
    text = (text or "").lower()
    text = re.sub("[ً-ٰٟـ]", "", text)  # harakat and tatweel
    text = re.sub("[أإآٱ]", "ا", text)
    return text.replace("ة", "ه").replace("ى", "ي").replace("ؤ", "و").replace("ئ", "ي")


def _is_arabic(word: str) -> bool:
    return bool(re.search("[؀-ۿ]", word))


def _strip_arabic_prefix(word: str) -> str:
    for prefix in _ARABIC_PREFIXES:
        if word.startswith(prefix) and len(word) - len(prefix) >= 3:
            return word[len(prefix):]
    return word


def _arabic_variants(word: str) -> set[str]:
    """The word, without "ال"-type prefixes, without a one-letter prefix (لتركيا -> تركيا), and with
    common plural / gender endings removed (عائلية -> عائل)."""
    forms = {word, _strip_arabic_prefix(word)}
    for w in list(forms):
        if w.startswith(_ARABIC_LETTER_PREFIXES) and len(w) >= 5:
            forms.add(_strip_arabic_prefix(w[1:]))
    for w in list(forms):
        for suffix in _ARABIC_SUFFIXES:
            if w.endswith(suffix) and len(w) - len(suffix) >= 3:
                forms.add(w[: -len(suffix)])
                break
    return {f for f in forms if len(f) >= 3}


def keyword_groups(text: str) -> list[set[str]]:
    groups: list[set[str]] = []
    for raw in re.findall(r"\w+", normalize(text)):
        if raw.isdigit():
            continue
        forms = _arabic_variants(raw) if _is_arabic(raw) else ({raw} if len(raw) >= 3 else set())
        if not forms or forms & _STOPWORDS:
            continue
        for f in list(forms):
            forms |= _SYNONYM_OF.get(f, set())
        if forms not in groups:
            groups.append(forms)
    return groups


def keywords(text: str) -> list[str]:
    """Main form of every meaningful word (kept for callers that need plain words)."""
    out = []
    for raw in re.findall(r"\w+", normalize(text)):
        w = _strip_arabic_prefix(raw)
        if len(w) >= 3 and w not in _STOPWORDS and not w.isdigit():
            out.append(w)
    return out


def _one_edit(a: str, b: str) -> bool:
    """True when a and b differ by at most one inserted, deleted or replaced letter."""
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) > len(b):
        a, b = b, a
    i = j = edits = 0
    while i < len(a) and j < len(b):
        if a[i] == b[j]:
            i += 1
            j += 1
            continue
        edits += 1
        if edits > 1:
            return False
        if len(a) == len(b):
            i += 1
        j += 1
    return edits + (len(b) - j) <= 1


class Matcher:
    """Prepared text to match keyword groups against."""

    def __init__(self, text: str):
        self.text = normalize(text)
        self.words = set(re.findall(r"\w+", self.text))

    def has(self, term: str) -> bool:
        if _is_arabic(term):
            return term in self.text
        if len(term) >= 5:
            if re.search(rf"\b{re.escape(term)}", self.text):
                return True
            return any(len(w) >= 5 and _one_edit(term, w) for w in self.words)
        return term in self.words

    def matches(self, group: set[str]) -> bool:
        return any(self.has(term) for term in group)
