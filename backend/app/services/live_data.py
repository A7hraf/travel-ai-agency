"""Live travel data for the AI's recommendations: real prices, photos, features and booking links.

* Hotels and flights come from Google Hotels and Google Flights through SerpApi; tours and activities from
  Viator's partner API. Each search counts as one use of the company's "live_search" feature.
* Keys: the platform owner's central keys, unless the owner gave a company its own key, which that company
  then uses. Keys are encrypted in the database and never sent to a browser.
* Without any key (free for everyone), the links the AI found on the web are opened by the server to check
  they work and to take the page's main photo. Only public addresses are opened, never the server's own
  network.
"""

from __future__ import annotations

import hashlib
import ipaddress
import logging
import re
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from html import unescape
from urllib.parse import urljoin, urlparse

import httpx
from fastapi import HTTPException
from sqlalchemy.orm import Session

from .. import platform_settings as ps
from ..addons import grant, has_addon, usage, use, user_may
from ..models import Company, User

log = logging.getLogger(__name__)

SERPAPI_URL = "https://serpapi.com/search.json"
SERPAPI_ACCOUNT_URL = "https://serpapi.com/account.json"
VIATOR_URL = "https://api.viator.com/partner/search/freetext"
VIATOR_SANDBOX_URL = "https://api.sandbox.viator.com/partner/search/freetext"
USER_AGENT = "Mozilla/5.0 (compatible; GhanjahBot/1.0; +https://ghanjah.onrender.com)"
PROVIDERS = {"serpapi": ("serpapi_key", "serpapi_api_key"), "viator": ("viator_key", "viator_api_key")}
SOURCES = {"google_hotels": "Google Hotels", "google_flights": "Google Flights", "viator": "Viator", "web": "Web"}
MAX_CANDIDATES = 10
VIATOR_CURRENCIES = {"USD", "EUR", "GBP", "AUD", "CAD", "CHF", "NZD", "SGD", "HKD", "JPY", "INR", "ZAR", "SEK", "NOK", "DKK"}


class LiveError(Exception):
    """A provider could not answer (bad key, limit reached at the provider, timeout…)."""


# --- Keys ---------------------------------------------------------------------------------------------

def keys(company: Company) -> dict[str, tuple[str, str]]:
    """provider -> (key, "company" or "platform"). A company's own key wins over the central one."""
    out = {}
    for provider, (column, setting) in PROVIDERS.items():
        own = (getattr(company, column, None) or "").strip()
        central = (ps.get_effective(setting) or "").strip()
        if own:
            out[provider] = (own, "company")
        elif central:
            out[provider] = (central, "platform")
    return out


def clean_key(value: str | None) -> str | None:
    """None: unchanged; "": remove; otherwise a plausible key."""
    if value is None:
        return None
    value = value.strip()
    if value and not re.fullmatch(r"[A-Za-z0-9_\-]{10,200}", value):
        raise HTTPException(422, "This doesn't look like an API key")
    return value


# --- HTTP (one place, so tests can replace it) ---------------------------------------------------------

def http(method: str, url: str, **kw) -> httpx.Response:
    with httpx.Client(timeout=kw.pop("timeout", 25.0), headers={"User-Agent": USER_AGENT}) as client:
        return client.request(method, url, **kw)


def _json(resp: httpx.Response, provider: str) -> dict:
    try:
        data = resp.json()
    except ValueError as exc:
        if resp.status_code in (401, 403):
            raise LiveError(f"{provider} refused the key ({resp.status_code})") from exc
        raise LiveError(f"{provider} sent an unreadable answer ({resp.status_code})") from exc
    if resp.status_code == 401 or resp.status_code == 403:
        said = (data.get("message") or data.get("error") or data.get("code")) if isinstance(data, dict) else None
        raise LiveError(f"{provider} refused the key ({resp.status_code}{': ' + str(said)[:120] if said else ''})")
    if resp.status_code == 429:
        raise LiveError(f"{provider} says the key has no searches left")
    if resp.status_code >= 400 or (isinstance(data, dict) and data.get("error")):
        msg = data.get("error") or data.get("message") if isinstance(data, dict) else None
        raise LiveError(f"{provider}: {str(msg or resp.status_code)[:160]}")
    return data if isinstance(data, dict) else {}


def _money(v) -> Decimal | None:
    try:
        d = Decimal(str(v))
    except (InvalidOperation, ValueError, TypeError):
        return None
    return d.quantize(Decimal("0.001")) if Decimal(0) < d < Decimal("100000000") else None


def _https(url) -> str | None:
    url = str(url or "").strip()
    return url[:500] if url.startswith("https://") and len(url) <= 500 else None


# --- Account (searches left on a SerpApi key) ------------------------------------------------------------

_account_cache: dict[str, tuple[float, dict]] = {}
_account_lock = threading.Lock()


def serpapi_account(key: str) -> dict:
    """{"left", "per_month", "used"} of a SerpApi key; cached for 10 minutes. Looking costs no search."""
    tag = hashlib.sha256(key.encode()).hexdigest()
    with _account_lock:
        hit = _account_cache.get(tag)
        if hit and time.monotonic() - hit[0] < 600:
            return hit[1]
    try:
        data = _json(http("GET", SERPAPI_ACCOUNT_URL, params={"api_key": key}, timeout=10.0), "SerpApi")
        out = {"left": data.get("total_searches_left", data.get("plan_searches_left")),
               "per_month": data.get("searches_per_month"), "used": data.get("this_month_usage"), "ok": True}
    except (LiveError, httpx.HTTPError) as exc:
        out = {"left": None, "per_month": None, "used": None, "ok": False, "error": str(exc)[:160]}
    with _account_lock:
        _account_cache[tag] = (time.monotonic(), out)
    return out


def forget_account(key: str) -> None:
    with _account_lock:
        _account_cache.pop(hashlib.sha256(key.encode()).hexdigest(), None)


# --- Searches -------------------------------------------------------------------------------------------

def google_hotels(key: str, place: str, check_in: date, check_out: date, adults: int, currency: str,
                  stars: int | None = None, rentals: bool = False) -> list[dict]:
    """Hotels in `place`. Holiday rentals only when the client asked for a villa or apartment (or too few hotels);
    well-reviewed places first. `stars`: the client's minimum class."""
    nights = max(1, (check_out - check_in).days)
    params = {"engine": "google_hotels", "q": f"{'places to stay' if rentals else 'hotels'} in {place}",
              "check_in_date": check_in.isoformat(), "check_out_date": check_out.isoformat(),
              "adults": max(1, min(adults, 10)), "currency": currency, "hl": "en", "api_key": key}
    if stars:
        params["hotel_class"] = ",".join(str(n) for n in range(stars, 6))
    data = _json(http("GET", SERPAPI_URL, params=params), "Google Hotels")
    page = (data.get("search_metadata") or {}).get("google_hotels_url")
    out = []
    for p in data.get("properties") or []:
        name = " ".join(str(p.get("name") or "").split())[:200]
        total = _money((p.get("total_rate") or {}).get("extracted_lowest"))
        night = _money((p.get("rate_per_night") or {}).get("extracted_lowest"))
        if not name or not (total or night):
            continue
        photos = [u for u in (_https(i.get("original_image") or i.get("thumbnail")) for i in p.get("images") or []) if u][:6]
        features = [str(a)[:60] for a in (p.get("amenities") or [])][:10]
        facts = {"rating": p.get("overall_rating"), "reviews": p.get("reviews"), "stars": p.get("extracted_hotel_class"),
                 "type": "vacation rental" if "rental" in str(p.get("type") or "").lower() else "hotel",
                 "features": features, "per_night": float(night) if night else None, "nights": nights,
                 "check_in": p.get("check_in_time"), "check_out": p.get("check_out_time"), "currency": currency,
                 "sold_by": [str(x.get("source"))[:60] for x in (p.get("prices") or []) if x.get("source")][:4],
                 "dates": f"{check_in.isoformat()} → {check_out.isoformat()}"}
        bits = [f"{facts['stars']}-star" if facts["stars"] else ("holiday rental" if facts["type"] != "hotel" else None),
                f"★ {facts['rating']} ({facts['reviews']} reviews)" if facts["rating"] else None,
                f"{nights} nights" + (f" · {night} {currency} a night" if night else ""), ", ".join(features[:5]) or None]
        out.append({"category": "hotel", "title": name, "provider": name, "price": total or night * nights,
                    "link": _https(p.get("link")) or _https(page), "photos": photos, "source": "google_hotels",
                    "facts": facts, "details": " · ".join(b for b in bits if b)})
    hotels = [c for c in out if c["facts"]["type"] == "hotel"]
    if not rentals and len(hotels) >= 3:
        out = hotels
    # Places with enough reviews first (a 5.0 from 4 reviews says little), keeping Google's order otherwise.
    out.sort(key=lambda c: (int(c["facts"].get("reviews") or 0) < 20, c["facts"]["type"] != "hotel"))
    return out[:MAX_CANDIDATES]


CABIN = {"economy": 1, "premium": 2, "business": 3, "first": 4}


def google_flights(key: str, origin: str, dest: str, depart: date, back: date | None, adults: int, currency: str,
                   cabin: str = "economy") -> list[dict]:
    params = {"engine": "google_flights", "departure_id": origin, "arrival_id": dest, "outbound_date": depart.isoformat(),
              "type": 1 if back else 2, "adults": max(1, min(adults, 9)), "currency": currency, "hl": "en",
              "travel_class": CABIN.get(cabin, 1), "api_key": key}
    if back:
        params["return_date"] = back.isoformat()
    data = _json(http("GET", SERPAPI_URL, params=params), "Google Flights")
    page = _https((data.get("search_metadata") or {}).get("google_flights_url"))
    out = []
    for trip in (data.get("best_flights") or []) + (data.get("other_flights") or []):
        legs = trip.get("flights") or []
        price = _money(trip.get("price"))
        if not legs or not price:
            continue
        airlines = list(dict.fromkeys(str(leg.get("airline") or "").strip() for leg in legs if leg.get("airline")))
        first, last = legs[0], legs[-1]
        dep, arr = first.get("departure_airport") or {}, last.get("arrival_airport") or {}
        stops = len(legs) - 1
        minutes = trip.get("total_duration")
        facts = {"airlines": airlines, "flight_numbers": [str(leg.get("flight_number"))[:12] for leg in legs if leg.get("flight_number")],
                 "depart": dep.get("time"), "arrive": arr.get("time"), "from": dep.get("id"), "to": arr.get("id"),
                 "stops": stops, "duration_min": minutes, "cabin": first.get("travel_class"),
                 "layovers": [f"{lv.get('name') or lv.get('id')} ({lv.get('duration')} min)" for lv in trip.get("layovers") or []][:3],
                 "round_trip": bool(back), "currency": currency, "travellers": adults}
        hours = f"{int(minutes) // 60}h {int(minutes) % 60:02d}m" if isinstance(minutes, int) else None
        title = f"{' + '.join(airlines) or 'Flight'} · {dep.get('id', origin)} {str(dep.get('time') or '')[-5:]} → " \
                f"{arr.get('id', dest)} {str(arr.get('time') or '')[-5:]}"
        bits = ["direct" if stops == 0 else f"{stops} stop" + ("s" if stops > 1 else ""), hours,
                "round-trip price" if back else "one way", ", ".join(facts["flight_numbers"]) or None]
        logo = _https(trip.get("airline_logo") or first.get("airline_logo"))
        out.append({"category": "flight", "title": title[:200], "provider": (airlines[0] if airlines else None),
                    "price": price, "link": page, "photos": [logo] if logo else [], "source": "google_flights",
                    "facts": facts, "details": " · ".join(b for b in bits if b)})
        if len(out) >= MAX_CANDIDATES:
            break
    return out


def viator(key: str, place: str, currency: str, travellers: int) -> list[dict]:
    body = {"searchTerm": place, "currency": currency,
            "searchTypes": [{"searchType": "PRODUCTS", "pagination": {"start": 1, "count": 15}}]}
    headers = {"exp-api-key": key, "Accept": "application/json;version=2.0", "Accept-Language": "en-US"}
    try:
        data = _json(http("POST", VIATOR_URL, json=body, headers=headers), "Viator")
    except LiveError as exc:
        if "refused the key" in str(exc) and _viator_sandbox_ok(headers):
            raise LiveError("Viator: this is a test (sandbox) key. Copy the production API key from your Viator "
                            "account (Tools → Affiliate API)") from exc
        raise
    products = data.get("products") or {}
    rows = products.get("results") if isinstance(products, dict) else products
    out = []
    for p in rows or []:
        title = " ".join(str(p.get("title") or "").split())[:200]
        pricing = p.get("pricing") or {}
        each = _money((pricing.get("summary") or {}).get("fromPrice"))
        if not title or not each:
            continue
        cur = str(pricing.get("currency") or currency)[:3]
        photos = []
        for img in p.get("images") or []:
            variants = [v for v in img.get("variants") or [] if _https(v.get("url"))]
            if variants:
                best = max((v for v in variants if (v.get("width") or 0) <= 1200), key=lambda v: v.get("width") or 0,
                           default=variants[-1])
                photos.append(best["url"])
            if len(photos) >= 5:
                break
        reviews = p.get("reviews") or {}
        dur = p.get("duration") or {}
        minutes = dur.get("fixedDurationInMinutes") or dur.get("variableDurationFromMinutes")
        facts = {"rating": round(float(reviews["combinedAverageRating"]), 1) if reviews.get("combinedAverageRating") else None,
                 "reviews": reviews.get("totalReviews"), "duration_min": minutes, "per_person": float(each),
                 "currency": cur, "travellers": travellers, "summary": str(p.get("description") or "")[:400],
                 "code": str(p.get("productCode") or "")[:30]}
        bits = [f"★ {facts['rating']} ({facts['reviews']} reviews)" if facts["rating"] else None,
                f"{int(minutes) // 60}h {int(minutes) % 60:02d}m" if isinstance(minutes, int) and minutes else None,
                f"from {each} {cur} per person"]
        out.append({"category": "activity", "title": title, "provider": "Viator", "price": each * max(1, travellers),
                    "link": _https(p.get("productUrl")), "photos": photos, "source": "viator", "facts": facts,
                    "details": " · ".join(b for b in bits if b)})
    out.sort(key=lambda c: -((c["facts"]["rating"] or 0) * min(c["facts"]["reviews"] or 0, 500)))
    return out[:MAX_CANDIDATES]


def _viator_sandbox_ok(headers: dict) -> bool:
    try:
        return http("POST", VIATOR_SANDBOX_URL, headers=headers, timeout=10.0, json={
            "searchTerm": "Muscat", "currency": "USD",
            "searchTypes": [{"searchType": "PRODUCTS", "pagination": {"start": 1, "count": 1}}]}).status_code < 400
    except httpx.HTTPError:
        return False


def test_keys(company: Company | None = None, central: bool = True) -> dict:
    """Tries each key once (one SerpApi account look-up, which costs no search, and one small Viator search)."""
    out = {}
    if central:
        k = {p: ((ps.get_effective(setting) or "").strip(), "platform") for p, (_, setting) in PROVIDERS.items()}
    else:
        k = {p: ((getattr(company, column) or "").strip(), "company") for p, (column, _) in PROVIDERS.items()}
    serp = k["serpapi"][0]
    if serp:
        forget_account(serp)
        a = serpapi_account(serp)
        out["serpapi"] = {"ok": a["ok"], "detail": (f"{a['left']} searches left" if a["ok"] else a.get("error"))}
    else:
        out["serpapi"] = {"ok": None, "detail": "No key"}
    vkey = k["viator"][0]
    if vkey:
        try:
            found = viator(vkey, "Muscat", "USD", 1)
            out["viator"] = {"ok": True, "detail": f"Working: {len(found)} activities found for Muscat"}
        except (LiveError, httpx.HTTPError) as exc:
            out["viator"] = {"ok": False, "detail": str(exc)[:240]}
    else:
        out["viator"] = {"ok": None, "detail": "No key"}
    return out


# --- Free: check a link and take the page's photo ------------------------------------------------------

def _public(host: str) -> bool:
    try:
        infos = socket.getaddrinfo(host, None)
    except (OSError, UnicodeError):
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
            ip = ip.ipv4_mapped
        if not ip.is_global:
            return False
    return bool(infos)


def safe_get(url: str, max_bytes: int = 400_000) -> tuple[int, str, str]:
    """(status, final address, start of the page). Only public http(s) addresses on the usual ports;
    redirects are followed by hand so each new address is checked too."""
    for _ in range(4):
        u = urlparse(url)
        if u.scheme not in ("http", "https") or not u.hostname or u.port not in (None, 80, 443) or u.username:
            raise LiveError("not a public web address")
        if not _public(u.hostname):
            raise LiveError("not a public web address")
        with httpx.Client(timeout=6.0, headers={"User-Agent": USER_AGENT, "Accept": "text/html,*/*"}) as client:
            with client.stream("GET", url, follow_redirects=False) as resp:
                if resp.status_code in (301, 302, 303, 307, 308) and resp.headers.get("location"):
                    url = urljoin(url, resp.headers["location"])
                    continue
                chunks, size = [], 0
                if "html" in resp.headers.get("content-type", "html"):
                    for chunk in resp.iter_bytes():
                        chunks.append(chunk)
                        size += len(chunk)
                        if size >= max_bytes:
                            break
                return resp.status_code, url, b"".join(chunks).decode(resp.encoding or "utf-8", "replace")
    raise LiveError("too many redirects")


FETCH = safe_get  # replaced in tests
_OG = re.compile(r"<meta[^>]+(?:property|name)=[\"'](?:og:image(?::secure_url)?|twitter:image)[\"'][^>]*>", re.I)
_CONTENT = re.compile(r"content=[\"']([^\"']+)[\"']", re.I)


def check_link(url: str) -> dict:
    """{"ok": True/False/None (unknown: the site refuses robots), "link", "photo"}."""
    try:
        status, final, page = FETCH(url)
    except (LiveError, httpx.HTTPError, OSError, ValueError) as exc:
        return {"ok": False, "why": str(exc)[:80]}
    if status in (401, 403, 405, 429, 999):  # big booking sites often refuse robots: the link may well work
        return {"ok": None, "link": url}
    if status >= 400:
        return {"ok": False, "why": f"page answered {status}"}
    photo = None
    for tag in _OG.findall(page or ""):
        m = _CONTENT.search(tag)
        if m:
            photo = _https(urljoin(final, unescape(m.group(1).strip())))
            if photo:
                break
    return {"ok": True, "link": _https(final) or url, "photo": photo}


def enrich(options: list[dict]) -> None:
    """Checks the links the AI gave (in parallel) and adds each page's photo. Broken links are removed."""
    todo = [o for o in options if o.get("link") and not o.get("source")]
    if not todo:
        return
    with ThreadPoolExecutor(max_workers=min(6, len(todo))) as pool:
        results = list(pool.map(lambda o: check_link(o["link"]), todo))
    for o, r in zip(todo, results):
        o["source"] = "web"
        o.setdefault("facts", {})["link_checked"] = r["ok"]
        if r["ok"] is False:
            o["link"] = None
        else:
            o["link"] = r.get("link") or o["link"]
            if r.get("photo"):
                o["photos"] = [r["photo"]]


# --- One planning session: which searches this employee may run now -------------------------------------

@dataclass
class LiveSession:
    db: Session
    user: User
    company: Company
    keys: dict = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    used: list[str] = field(default_factory=list)

    @classmethod
    def start(cls, db: Session, user: User, company: Company) -> LiveSession:
        s = cls(db=db, user=user, company=company)
        if has_addon(company, "live_search") and user_may(user, "live_search"):
            s.keys = keys(company)
        return s

    def ready(self, provider: str) -> bool:
        return provider in self.keys

    def charge(self, source: str) -> bool:
        """Counts one search; False when the company's searches for this month are used up."""
        try:
            use(self.db, self.user, "live_search")
        except HTTPException as exc:
            self.notes.append("limit" if exc.status_code == 429 else "not allowed")
            self.keys = {}
            return False
        self.used.append(source)
        return True


def status(db: Session, company: Company) -> dict:
    """What a company may see: searches used and left this month, and whose key is used (never the key)."""
    g = grant(company, "live_search")
    used = usage(db, company.id, "live_search", g) if g.on else 0
    k = keys(company)
    out = {"on": g.on, "limit": g.limit, "used": used, "left": (max(0, g.limit - used) if g.limit is not None else None),
           "period": g.period, "providers": {p: owner for p, (_, owner) in k.items()}, "key_left": None}
    if k.get("serpapi", (None, None))[1] == "company":
        out["key_left"] = serpapi_account(k["serpapi"][0]).get("left")
    return out


def default_dates(depart: date | None, back: date | None) -> tuple[date | None, date | None]:
    if depart is None:
        return None, None
    return depart, back if back and back > depart else depart + timedelta(days=3)
