import { AirplaneTilt } from "../Icon";
import { Money, type Lang } from "../Money";
import { Poster, placeOf } from "../Poster";
import type { StorefrontText } from "../../i18n";
import type { ChatCard } from "../../types";

type PackageCard = Extract<ChatCard, { type: "package" }>;
type QuoteCard = Extract<ChatCard, { type: "quote" }>;
type TicketCard = Extract<ChatCard, { type: "ticket" }>;

/** Trip suggested by the AI: mini poster, "View trip" and "Book this trip". */
export function ChatPackageCard({ card, t, lang, onView, onBook, disabled }: {
  card: PackageCard; t: StorefrontText; lang: Lang; onView?: () => void; onBook: () => void; disabled?: boolean;
}) {
  return (
    <div className="sf-ccard sf-cpkg">
      <Poster destination={card.destination} country={card.country} title={card.title} imageUrl={card.image_url}
        stamp={false} route={false} className="sf-cpkg-poster">
        <div className="sf-cpkg-dest" dir="auto">{card.destination}</div>
      </Poster>
      <div className="sf-cpkg-body">
        <div className="sf-cpkg-title" dir="auto">{card.title}</div>
        <div className="sf-cpkg-meta">
          {t.days(card.duration_days)} · <Money value={card.price_per_person} currency={card.currency} lang={lang} /> {t.perAdult}
        </div>
        <div className={`sf-cpkg-actions ${onView ? "" : "sf-one"}`}>
          {onView && <button type="button" className="sf-btn-surface" onClick={onView}>{t.viewTrip}</button>}
          <button type="button" className="sf-btn-cyan" onClick={onBook} disabled={disabled}>{t.bookThis}</button>
        </div>
      </div>
    </div>
  );
}

/** Booking summary from the booking system, with Confirm / Change while it waits for an answer. */
export function ChatQuoteCard({ card, t, lang, active, onConfirm, onChange, disabled }: {
  card: QuoteCard; t: StorefrontText; lang: Lang; active: boolean; onConfirm: () => void; onChange: () => void; disabled?: boolean;
}) {
  const pax = card.travelers ? t.pax(card.travelers.adults ?? 1, card.travelers.children ?? 0) : "—";
  return (
    <div className="sf-ccard sf-quote">
      <div className="sf-quote-kicker">{t.summary}</div>
      <div className="sf-quote-row"><span>{t.sPkg}</span><span dir="auto">{card.package}</span></div>
      <div className="sf-quote-row"><span>{t.sDate}</span><span>{card.departure_date ? t.date(card.departure_date) : "—"}</span></div>
      <div className="sf-quote-row"><span>{t.sPax}</span><span>{pax}</span></div>
      <div className="sf-quote-total">
        <span>{t.sTotal}</span>
        <strong><Money value={card.total_price} currency={card.currency} lang={lang} /></strong>
      </div>
      {active && (
        <div className="sf-quote-actions">
          <button type="button" className="sf-btn-cyan sf-big" onClick={onConfirm} disabled={disabled}>{t.confirmBooking}</button>
          <button type="button" className="sf-btn-surface" onClick={onChange} disabled={disabled}>{t.change}</button>
        </div>
      )}
    </div>
  );
}

/** The boarding pass: booking request received, with the reference on the perforated stub. */
export function ChatTicketCard({ card, t }: { card: TicketCard; t: StorefrontText }) {
  const iata = placeOf(card.destination, card.package).iata;
  const sub = [card.departure_date ? t.date(card.departure_date) : null,
    card.travelers ? t.pax(card.travelers.adults ?? 1, card.travelers.children ?? 0) : null].filter(Boolean).join(" · ");
  return (
    <div className="sf-ccard sf-pass" dir="ltr" role="group" aria-label={`${t.booked} · ${t.bookedRef} ${card.ticket_reference}`}>
      <div className="sf-pass-main">
        <div className="sf-pass-kicker" dir="auto">{t.booked}</div>
        <div className="sf-pass-route">
          <span>MCT</span><i /><AirplaneTilt weight="fill" className="sf-pass-plane" /><i /><span>{iata}</span>
        </div>
        {sub && <div className="sf-pass-sub" dir="auto">{sub}</div>}
      </div>
      <div className="sf-pass-stub">
        <span className="sf-pass-label" dir="auto">{t.bookedRef}</span>
        <span className="sf-pass-ref">{card.ticket_reference}</span>
      </div>
      <span className="sf-pass-notch sf-top" aria-hidden="true" />
      <span className="sf-pass-notch sf-bottom" aria-hidden="true" />
    </div>
  );
}
