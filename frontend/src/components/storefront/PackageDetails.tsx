import { AirplaneTilt, Armchair, ArrowLeft, Bed, CalendarBlank, CheckCircle, Sparkle, X, XCircle } from "../Icon";
import { Money, type Lang } from "../Money";
import { Poster, placeOf } from "../Poster";
import type { StorefrontText } from "../../i18n";
import type { TravelPackage } from "../../types";
import { stars, todayIso } from "./shared";

function Facts({ p, t }: { p: TravelPackage; t: StorefrontText }) {
  const low = p.seats_available != null && p.seats_available <= 6;
  return (
    <div className="sf-facts">
      <span className="sf-fact"><CalendarBlank className="sf-fact-icon" />{t.days(p.duration_days)}</span>
      {p.hotel_name && (
        <span className="sf-fact"><Bed className="sf-fact-icon" /><bdi>{p.hotel_name}</bdi>{p.hotel_stars ? <span className="sf-stars"> {stars(p.hotel_stars)}</span> : null}</span>
      )}
      {p.seats_available != null && (
        <span className={`sf-fact ${low ? "sf-low" : ""}`}><Armchair className="sf-fact-icon" />{low ? t.seatsLow(p.seats_available) : t.seatsLeft(p.seats_available)}</span>
      )}
    </div>
  );
}

function Lists({ p, t }: { p: TravelPackage; t: StorefrontText }) {
  return (
    <>
      {p.includes.length > 0 && (
        <>
          <h3 className="sf-pd-h">{t.included}</h3>
          <ul className="sf-inc">{p.includes.map((x) => <li key={x}><CheckCircle className="sf-inc-icon" /><bdi>{x}</bdi></li>)}</ul>
        </>
      )}
      {p.excludes.length > 0 && (
        <>
          <h3 className="sf-pd-h">{t.notIncluded}</h3>
          <ul className="sf-inc sf-exc">{p.excludes.map((x) => <li key={x}><XCircle className="sf-inc-icon" /><bdi>{x}</bdi></li>)}</ul>
        </>
      )}
    </>
  );
}

/** Phone: the package screen pushed in from the inline end. */
export function PhonePackage({ p, t, lang, agent, onBack, onBook }: {
  p: TravelPackage; t: StorefrontText; lang: Lang; agent: string; onBack: () => void; onBook: () => void;
}) {
  const iata = placeOf(p.destination, p.country, p.title).iata;
  const today = todayIso();
  return (
    <>
      <div className="sf-screen-scroll">
        <Poster destination={p.destination} country={p.country} title={p.title} imageUrl={p.image_url} stamp={false} route={false} className="sf-pd-hero">
          <div className="sf-pd-fade" />
          <button type="button" className="icon-btn glass sf-pd-back" onClick={onBack} aria-label={t.back}><ArrowLeft className="flip" /></button>
          <div className="sf-pd-route" dir="ltr" aria-hidden="true">
            <span>MCT</span><i /><AirplaneTilt weight="fill" className="sf-pd-plane" /><i /><span>{iata}</span>
          </div>
        </Poster>
        <div className="sf-pd-body">
          <div className="sf-kicker-cyan" dir="auto">{p.destination} · {p.country}</div>
          <h1 className="sf-pd-title" dir="auto">{p.title}</h1>
          <Facts p={p} t={t} />
          <div className={`sf-price-tiles ${p.child_price == null ? "sf-one" : ""}`}>
            <div className="sf-price-tile"><div className="sf-price-big"><Money value={p.price_per_person} currency={p.currency} lang={lang} /></div><div className="sf-price-cap">{t.perAdult}</div></div>
            {p.child_price != null && (
              <div className="sf-price-tile"><div className="sf-price-big"><Money value={p.child_price} currency={p.currency} lang={lang} /></div><div className="sf-price-cap">{t.perChild}</div></div>
            )}
          </div>
          <h3 className="sf-pd-h sf-first">{t.departures}</h3>
          <div className="sf-dates">
            {p.departure_dates.length
              ? p.departure_dates.map((d) => <span key={d} className={`sf-date ${d < today ? "sf-past" : ""}`}>{t.date(d)}</span>)
              : <span className="sf-date">{t.flexible}</span>}
          </div>
          {p.description && <p className="sf-pd-desc" dir="auto">{p.description}</p>}
          <Lists p={p} t={t} />
        </div>
      </div>
      <div className="sf-pd-foot">
        <div className="sf-pd-from"><span>{t.from}</span><strong><Money value={p.price_per_person} currency={p.currency} lang={lang} /></strong></div>
        <button type="button" className="sf-cta" onClick={onBook}><Sparkle />{t.bookWith(agent)}</button>
      </div>
    </>
  );
}

/** Desktop: the package window (poster on the left, details on the right). */
export function WebPackage({ p, t, lang, agent, onClose, onBook }: {
  p: TravelPackage; t: StorefrontText; lang: Lang; agent: string; onClose: () => void; onBook: () => void;
}) {
  const low = p.seats_available != null && p.seats_available <= 6;
  const meta = [t.days(p.duration_days), p.hotel_name ? `${p.hotel_name}${p.hotel_stars ? ` ${stars(p.hotel_stars)}` : ""}` : null].filter(Boolean).join(" · ");
  const today = todayIso();
  return (
    <div className="sf-pkgwin">
      <Poster destination={p.destination} country={p.country} title={p.title} imageUrl={p.image_url} stamp={false} className="sf-pkgwin-poster">
        <div className="sf-pkgwin-dest" dir="auto">{p.destination}</div>
      </Poster>
      <div className="sf-pkgwin-body">
        <div className="sf-pkgwin-top">
          <span className="sf-kicker-cyan" dir="auto">{p.country}</span>
          <button type="button" className="sf-round-btn sf-filled" onClick={onClose} aria-label={t.closeWindow}><X /></button>
        </div>
        <div className="sf-pkgwin-title" dir="auto">{p.title}</div>
        <div className="sf-pkgwin-meta">
          {meta}
          {p.seats_available != null && <> · <span className={low ? "sf-low" : ""}>{low ? t.seatsLow(p.seats_available) : t.seatsLeft(p.seats_available)}</span></>}
        </div>
        {p.description && <p className="sf-pkgwin-desc" dir="auto">{p.description}</p>}
        {p.departure_dates.length > 0 && (
          <div className="sf-dates sf-sm">
            {p.departure_dates.map((d) => <span key={d} className={`sf-date ${d < today ? "sf-past" : ""}`}>{t.date(d)}</span>)}
          </div>
        )}
        <div className="sf-pkgwin-lists">
          {p.includes.length > 0 && <div><div className="sf-pkgwin-h">{t.included}</div><ul className="sf-inc sf-sm">{p.includes.map((x) => <li key={x}><CheckCircle className="sf-inc-icon" /><bdi>{x}</bdi></li>)}</ul></div>}
          {p.excludes.length > 0 && <div><div className="sf-pkgwin-h">{t.notIncluded}</div><ul className="sf-inc sf-sm sf-exc">{p.excludes.map((x) => <li key={x}><XCircle className="sf-inc-icon" /><bdi>{x}</bdi></li>)}</ul></div>}
        </div>
        <div className="sf-pkgwin-foot">
          <div className="sf-pkgwin-price"><Money value={p.price_per_person} currency={p.currency} lang={lang} /></div>
          <span className="sf-muted-sm">{t.perAdult}</span>
          {p.child_price != null && <span className="sf-muted-sm">· <Money value={p.child_price} currency={p.currency} lang={lang} /> {t.perChild}</span>}
          <button type="button" className="sf-cta" onClick={onBook}><Sparkle />{t.bookWith(agent)}</button>
        </div>
      </div>
    </div>
  );
}
