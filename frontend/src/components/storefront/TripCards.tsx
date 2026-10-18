import { Sparkle } from "../Icon";
import { Money, type Lang } from "../Money";
import { Poster, placeOf } from "../Poster";
import type { StorefrontText } from "../../i18n";
import type { TravelPackage } from "../../types";
import { onCardKey, stars } from "./shared";

interface CardProps { p: TravelPackage; t: StorefrontText; lang: Lang; onOpen: () => void }

/** Phone: large featured poster in the carousel. */
export function FeaturedPoster({ p, t, lang, onOpen }: CardProps) {
  return (
    <article className="sf-feat" tabIndex={0} role="button" aria-label={t.openPackage(p.title)} onClick={onOpen} onKeyDown={onCardKey(onOpen)}>
      <Poster destination={p.destination} country={p.country} title={p.title} imageUrl={p.image_url} className="sf-feat-poster">
        <div className="poster-body">
          <div className="poster-country">{p.country}</div>
          <div className="poster-name" dir="auto">{p.destination}</div>
          <div className="poster-foot"><span>{t.days(p.duration_days)}</span><Money value={p.price_per_person} currency={p.currency} lang={lang} /></div>
        </div>
      </Poster>
    </article>
  );
}

/** Phone (and the "list" layout): row with a mini poster, place, title, days · price and a Book pill. */
export function OfferRow({ p, t, lang, onOpen, onBook }: CardProps & { onBook: () => void }) {
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
          <div className="sf-offer-meta">{t.days(p.duration_days)} · <Money value={p.price_per_person} currency={p.currency} lang={lang} /></div>
        </div>
      </div>
      <button type="button" className="sf-book-pill" onClick={onBook} aria-label={`${t.book} · ${p.title}`}>{t.book}</button>
    </div>
  );
}

/** Desktop grid: tall poster card (hover lift and glow). */
export function WebPoster({ p, t, lang, onOpen }: CardProps) {
  return (
    <article className="sf-wposter" tabIndex={0} role="button" aria-label={t.openPackage(p.title)} onClick={onOpen} onKeyDown={onCardKey(onOpen)}>
      <Poster destination={p.destination} country={p.country} title={p.title} imageUrl={p.image_url} className="sf-wposter-art">
        <div className="poster-body">
          <div className="poster-country">{p.country}</div>
          <div className="poster-name" dir="auto">{p.destination}</div>
          <div className="poster-foot"><span className="sf-wposter-title" dir="auto">{p.title}</span><Money value={p.price_per_person} currency={p.currency} lang={lang} /></div>
        </div>
      </Poster>
    </article>
  );
}

/** Desktop "list" layout: poster on the side, details and a Book button. */
export function WebRow({ p, t, lang, onOpen, onBook, agent }: CardProps & { onBook: () => void; agent: string }) {
  return (
    <article className="sf-wrow" onClick={onOpen}>
      <Poster destination={p.destination} country={p.country} title={p.title} imageUrl={p.image_url} className="sf-wrow-art">
        <div className="poster-body"><div className="poster-name" dir="auto">{p.destination}</div></div>
      </Poster>
      <div className="sf-wrow-body">
        <div className="sf-kicker-cyan">{p.country}</div>
        <h3 className="sf-wrow-title" dir="auto"><button type="button" onClick={(e) => { e.stopPropagation(); onOpen(); }} aria-label={t.openPackage(p.title)}>{p.title}</button></h3>
        <div className="sf-wrow-meta">{t.days(p.duration_days)}{p.hotel_name ? ` · ${p.hotel_name}` : ""}{p.hotel_stars ? ` ${stars(p.hotel_stars)}` : ""}</div>
        {p.description && <p className="sf-wrow-desc" dir="auto">{p.description}</p>}
        <div className="sf-wrow-foot">
          <span className="sf-wrow-price"><Money value={p.price_per_person} currency={p.currency} lang={lang} /></span>
          <span className="sf-muted-sm">{t.perAdult}</span>
          <button type="button" className="sf-cta sf-sm" onClick={(e) => { e.stopPropagation(); onBook(); }}><Sparkle />{t.bookWith(agent)}</button>
        </div>
      </div>
    </article>
  );
}
