"""Ad blockers hide elements whose class names look like adverts (EasyList hides .ad-card, .ad-head, …).
Staff pages once went blank for owners with an ad blocker, so such names must never come back."""

import re
from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "src"
ADVERT_LIKE = re.compile(r"\.(ad|ads|adv|advert|advertisement|sponsor|sponsored|adbox|adslot|banner-ad)(?=[-_\s.{:,>)])", re.I)


def test_no_advert_like_class_names():
    if not FRONTEND.is_dir():  # backend-only checkout
        return
    found = []
    for path in FRONTEND.rglob("*.css"):
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if ADVERT_LIKE.search(line):
                found.append(f"{path.relative_to(FRONTEND)}:{n}: {line.strip()[:80]}")
    for path in list(FRONTEND.rglob("*.tsx")) + list(FRONTEND.rglob("*.ts")):
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"""[\s"'`{(](ad|ads|advert|sponsor)-[a-z]""", line):
                found.append(f"{path.relative_to(FRONTEND)}:{n}: {line.strip()[:80]}")
    assert not found, "Rename these class names (ad blockers hide them):\n" + "\n".join(found)
