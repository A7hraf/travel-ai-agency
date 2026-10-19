import { Armchair, Bed, CalendarBlank, Clock, Sparkle } from "../Icon";
import { Money, type Lang } from "../Money";
import { Poster, placeOf } from "../Poster";
import type { StorefrontText } from "../../i18n";
import type { CardDesign, TravelPackage } from "../../types";
import { onCardKey, stars, todayIso } from "./shared";

interface CardProps { p: TravelPackage; t: StorefrontText; lang: Lang; cards: CardDesign; onOpen: () => void }

/** The facts the agency chose to show on its cards (duration, hotel, next date, seats left, tags). */
export function CardFacts({ p, t, cards, skipDuration, className = "" }: {
  p: TravelPackage; t: StorefrontText; cards: CardDesign; skipDuration?: boolean; className?: string;
}) {
  const today = todayIso();
  const next = cards.show_next_date ? p.departure_dates.find((d) => d >= today) : undefined;
  const seats = cards.show_seats && p.seats_available != null && p.seats_available > 0 ? p.seats_available : null;
  const tags = cards.show_tags ? p.tags.slice(0, 3) : [];
  const items = [
    cards.show_duration && !skipDuration ? <span key="d"><Clock aria-hidden="true" />{t.days(p.duration_days)}</span> : null,
    cards.show_hotel && p.hotel_name ? <span key="h"><Bed aria-hidden="true" /><bdi>{p.hotel_name}</bdi>{p.hotel_stars ? ` ${stars(p.hotel_stars)}` : ""}</span> : null,
    next ? <span key="n"><CalendarBlank aria-hidden="true" />{t.date(next)}</span> : null,
    seats != null ? <span key="s" className={seats <= 6 ? "sf-low" : ""}><Armchair aria-hidden="true" />{seats <= 6 ? t.seatsLow(seats) : t.seatsLeft(seats)}</span> : null,
  ].filter(Boolean);
  if (!items.length && !tags.length) return null;
  return (
    <div className={`sf-cfacts ${className}`}>
      {items}
      {tags.map((x) => <span key={`t-${x}`} className="sf-ctag"><bdi>{x}</bdi></span>)}
    </div>
  );
}

/** Price, with "per person" when the agency wants it. */
export function CardPrice({ p, t, lang, cards, className = "" }: { p: TravelPackage; t: StorefrontText; lang: Lang; cards: CardDesign; className?: string }) {
  if (!cards.show_price) return null;
  return (
    <span className={`sf-cprice ${className}`}>
      <Money value={p.price_per_person} currency={p.currency} lang={lang} />
      {cards.per_person && <small className="sf-cper">{t.perPerson}</small>}
    </span>
  );
}

/** Phone: large featured poster in the carousel. */
export function FeaturedPoster({ p, t, lang, cards, onOpen }: CardProps) {
  return (
    <article className="sf-feat" tabIndex={0} role="button" aria-label={t.openPackage(p.title)} onClick={onOpen} onKeyDown={onCardKey(onOpen)}>
      <Poster destination={p.destination} country={p.country} title={p.title} imageUrl={p.image_url} className="sf-feat-poster">
        <div className="poster-body">
          <div className="poster-country">{p.country}</div>
          <div className="poster-name" dir="auto">{p.destination}</div>
          <CardFacts p={p} t={t} cards={cards} skipDuration className="sf-on-poster" />
          <div className="poster-foot">
            <span>{cards.show_duration ? t.days(p.duration_days) : ""}</span>
            <CardPrice p={p} t={t} lang={lang} cards={cards} />
          </div>
        </div>
      </Poster>
    </article>
  );
}

/** Phone (and the "compact" style): row with a mini poster, place, title, facts · price and a Book pill. */
export function OfferRow({ p, t, lang, cards, onOpen, onBook }: CardProps & { onBook: () => void }) {
  const iata = placeOf(p.destination, p.country, p.title).iata;
  return (
    <div className="sf-offer">
      <div className="sf-offer-open" tabIndex={0} role="button" aria-label={t.openPackage(p.title)} onClick={onOpen} onKeyDown={onCardKey(onOpen)}>
        <Poster destination={p.destination} country={p.country} title={p.title} imageUrl={p.image_url} stamp={false} route={false} className="sf-mini">
          <span className="sf-mini-code" dir="ltr">{iata}</span>
        </Poster>
        <div className="sf-offer-text">
          <div className="sf-offer-country">{p.country}</div>
          <div className="sf-offer-title" dir="auto">{p.title}</div>
          <div className="sf-offer-meta">
            {cards.show_duration && t.days(p.duration_days)}
            {cards.show_duration && cards.show_price && " · "}
            <CardPrice p={p} t={t} lang={lang} cards={cards} />
          </div>
          <CardFacts p={p} t={t} cards={cards} skipDuration className="sf-sm" />
        </div>
      </div>
      {cards.show_button && <button type="button" className="sf-book-pill" onClick={onBook} aria-label={`${t.book} · ${p.title}`}>{t.book}</button>}
    </div>
  );
}

/** Desktop grid: tall poster card (hover lift and glow). */
export function WebPoster({ p, t, lang, cards, onOpen }: CardProps) {
  return (
    <article className="sf-wposter" tabIndex={0} role="button" aria-label={t.openPackage(p.title)} onClick={onOpen} onKeyDown={onCardKey(onOpen)}>
      <Poster destination={p.destination} country={p.country} title={p.title} imageUrl={p.image_url} className="sf-wposter-art">
        <div className="poster-body">
          <div className="poster-country">{p.country}</div>
          <div className="poster-name" dir="auto">{p.destination}</div>
          <CardFacts p={p} t={t} cards={cards} className="sf-on-poster" />
          <div className="poster-foot"><span className="sf-wposter-title" dir="auto">{p.title}</span><CardPrice p={p} t={t} lang={lang} cards={cards} /></div>
        </div>
      </Poster>
    </article>
  );
}

/** Photo-first card (phone and desktop): photo or destination art on top, details and a Book button below. */
export function PhotoCard({ p, t, lang, cards, onOpen, onBook, agent, phone }: CardProps & { onBook: () => void; agent: string; phone?: boolean }) {
  return (
    <article className="sf-pcard" tabIndex={0} role="button" aria-label={t.openPackage(p.title)} onClick={onOpen} onKeyDown={onCardKey(onOpen)}>
      <Poster destination={p.destination} country={p.country} title={p.title} imageUrl={p.image_url} stamp={false} className="sf-pcard-art">
        <div className="poster-body"><div className="poster-name" dir="auto">{p.destination}</div></div>
      </Poster>
      <div className="sf-pcard-body">
        <div className="sf-offer-country">{p.country}</div>
        <h3 className="sf-pcard-title" dir="auto">{p.title}</h3>
        <CardFacts p={p} t={t} cards={cards} />
        <div className="sf-pcard-foot">
          <CardPrice p={p} t={t} lang={lang} cards={cards} className="sf-big" />
          {cards.show_button && (
            <button type="button" className="sf-btn-cyan" onClick={(e) => { e.stopPropagation(); onBook(); }}>
              {phone ? t.book : <><Sparkle />{t.bookWith(agent)}</>}
            </button>
          )}
        </div>
      </div>
    </article>
  );
}

/** Desktop "compact" style: poster on the side, details and a Book button. */
export function WebRow({ p, t, lang, cards, onOpen, onBook, agent }: CardProps & { onBook: () => void; agent: string }) {
  return (
    <article className="sf-wrow" onClick={onOpen}>
      <Poster destination={p.destination} country={p.country} title={p.title} imageUrl={p.image_url} className="sf-wrow-art">
        <div className="poster-body"><div className="poster-name" dir="auto">{p.destination}</div></div>
      </Poster>
      <div className="sf-wrow-body">
        <div className="sf-kicker-cyan">{p.country}</div>
        <h3 className="sf-wrow-title" dir="auto"><button type="button" onClick={(e) => { e.stopPropagation(); onOpen(); }} aria-label={t.openPackage(p.title)}>{p.title}</button></h3>
        <CardFacts p={p} t={t} cards={cards} className="sf-wrow-meta" />
        {p.description && <p className="sf-wrow-desc" dir="auto">{p.description}</p>}
        <div className="sf-wrow-foot">
          <CardPrice p={p} t={t} lang={lang} cards={cards} className="sf-wrow-price" />
          {cards.show_button && <button type="button" className="sf-cta sf-sm" onClick={(e) => { e.stopPropagation(); onBook(); }}><Sparkle />{t.bookWith(agent)}</button>}
        </div>
      </div>
    </article>
  );
}
