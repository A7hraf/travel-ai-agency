import { useEffect, useState } from "react";
import { get } from "../../api";
import { useI18n } from "../../lang";
import { ArrowSquareOut, CheckCircle, Clock, Globe, Lightning, Star, WarningCircle } from "../Icon";

/** The live-data parts of a recommendation card: photos, where the price comes from, rating, features,
 *  flight times and the booking button. Used on the request page and on business requests. */

export interface LiveFacts {
  rating?: number | null; reviews?: number | null; stars?: number | null; features?: string[]; per_night?: number | null;
  nights?: number; per_person?: number | null; currency?: string; sold_by?: string[]; dates?: string;
  airlines?: string[]; flight_numbers?: string[]; depart?: string | null; arrive?: string | null; from?: string; to?: string;
  stops?: number; duration_min?: number | null; layovers?: string[]; round_trip?: boolean; summary?: string;
  link_checked?: boolean | null; site?: string;
}
export interface LiveOption {
  title: string; link: string | null; image_url: string | null; photos?: string[] | null; source?: string | null; facts?: LiveFacts | null;
}

const SOURCE: Record<string, string> = { google_hotels: "Google Hotels", google_flights: "Google Flights", viator: "Viator" };
export const isLive = (o: { source?: string | null }) => !!o.source && o.source !== "web";

function hours(min?: number | null) {
  if (!min) return null;
  return `${Math.floor(min / 60)}h ${String(min % 60).padStart(2, "0")}m`;
}

export function LivePhotos({ option }: { option: LiveOption }) {
  const { t } = useI18n();
  const all = [option.image_url, ...(option.photos ?? [])].filter(Boolean) as string[];
  const [shown, setShown] = useState(0);
  const [broken, setBroken] = useState<string[]>([]);
  const ok = all.filter((u) => !broken.includes(u));
  if (!ok.length) return null;
  const main = ok[Math.min(shown, ok.length - 1)];
  const logo = option.source === "google_flights";
  return (
    <div className={`gx-live-photos ${logo ? "logo" : ""}`}>
      <img src={main} alt={option.title} loading="lazy" referrerPolicy="no-referrer" onError={() => setBroken([...broken, main])} />
      {ok.length > 1 && !logo && (
        <div className="gx-live-thumbs" role="group" aria-label={t("Photos")}>
          {ok.slice(0, 5).map((u, i) => (
            <button key={u} type="button" className={u === main ? "on" : ""} aria-label={t("Photo {n}", { n: i + 1 })} onClick={() => setShown(i)}>
              <img src={u} alt="" loading="lazy" referrerPolicy="no-referrer" onError={() => setBroken([...broken, u])} />
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export function LiveDetails({ option }: { option: LiveOption }) {
  const { t, lang } = useI18n();
  const f = option.facts ?? {};
  const loc = lang === "ar" ? "ar-OM" : "en-GB";
  const time = (v?: string | null) => (v ? v.slice(-5) : "");
  const live = isLive(option);
  return (
    <div className="gx-live">
      <div className="gx-live-badges small">
        {live && <span className="gx-live-src"><Lightning weight="fill" /> {t("Live price")} · {SOURCE[option.source!] ?? option.source}</span>}
        {option.source === "web" && f.site && <span className="gx-live-site"><Globe /> {t("Found by the AI on {site}", { site: f.site })}</span>}
        {option.source === "web" && f.link_checked === true && <span className="gx-live-ok"><CheckCircle weight="fill" /> {t("Link checked")}</span>}
        {option.source === "web" && f.link_checked === null && <span className="muted"><WarningCircle /> {t("Site doesn't allow checking: open it to confirm")}</span>}
        {option.source === "web" && f.link_checked === false && <span className="gx-live-bad"><WarningCircle /> {t("The AI's link didn't work: removed")}</span>}
        {f.rating != null && <span className="gx-live-rating"><Star weight="fill" /> {f.rating}{f.reviews != null && <span className="muted"> ({Number(f.reviews).toLocaleString(loc)})</span>}</span>}
        {f.stars != null && <span>{"★".repeat(Math.min(5, Number(f.stars)))} <span className="muted">{t("{n}-star", { n: f.stars })}</span></span>}
      </div>
      {option.source === "google_flights" && (
        <div className="gx-live-flight small">
          <strong className="tnum" dir="ltr">{f.from} {time(f.depart)} → {f.to} {time(f.arrive)}</strong>
          {hours(f.duration_min) && <span><Clock /> {hours(f.duration_min)}</span>}
          <span>{f.stops === 0 ? t("Direct") : f.stops === 1 ? t("1 stop") : t("{n} stops", { n: f.stops ?? 0 })}</span>
          {!!f.layovers?.length && <span className="muted" dir="auto">{t("via")} {f.layovers.join(", ")}</span>}
          {!!f.flight_numbers?.length && <span className="muted tnum" dir="ltr">{f.flight_numbers.join(" · ")}</span>}
          <span className="muted">{f.round_trip ? t("Round-trip price") : t("One way")}</span>
        </div>
      )}
      {option.source === "viator" && (
        <div className="gx-live-flight small">
          {hours(f.duration_min) && <span><Clock /> {hours(f.duration_min)}</span>}
          {f.per_person != null && <span className="tnum">{t("from {p} per person", { p: `${f.per_person} ${f.currency ?? ""}` })}</span>}
        </div>
      )}
      {option.source === "google_hotels" && (f.per_night != null || f.dates) && (
        <div className="gx-live-flight small">
          {f.per_night != null && <span className="tnum">{t("{p} a night", { p: `${f.per_night} ${f.currency ?? ""}` })} · {t("{n} nights", { n: f.nights ?? 1 })}</span>}
          {f.dates && <span className="muted tnum" dir="ltr">{f.dates}</span>}
          {!!f.sold_by?.length && <span className="muted">{t("Sold by")} {f.sold_by.join(", ")}</span>}
        </div>
      )}
      {!!f.features?.length && (
        <ul className="gx-live-features small">{f.features.slice(0, 8).map((x) => <li key={x} dir="auto">{x}</li>)}</ul>
      )}
      {f.summary && <p className="muted small gx-live-summary" dir="auto">{f.summary}</p>}
      {option.link && (
        <a className="btn btn-sm btn-soft gx-live-book" href={option.link} target="_blank" rel="noreferrer noopener">
          {live ? t("View and book") : t("Open the page")} <ArrowSquareOut />
        </a>
      )}
    </div>
  );
}

/** "12 of 20 live searches left this month" next to the AI button. */
export function LiveUsage() {
  const { t } = useI18n();
  const [s, setS] = useState<{ on: boolean; used: number; limit: number | null; left: number | null; providers: Record<string, string>; key_left: number | null } | null>(null);
  useEffect(() => { get<typeof s>("/api/live-data").then(setS).catch(() => {}); }, []);
  if (!s || !s.on || !Object.keys(s.providers).length) return null;
  const own = s.providers.serpapi === "company";
  return (
    <span className={`gx-live-usage small ${s.left === 0 ? "out" : ""}`} title={t("Real prices, photos and booking links from Google Hotels, Google Flights and Viator")}>
      <Lightning weight="fill" />
      {s.left === null ? t("Live searches: {n} used this month", { n: s.used }) : t("Live searches left: {n} of {m} this month", { n: s.left, m: s.limit ?? 0 })}
      {own && s.key_left != null && <> · {t("your key: {n} left", { n: s.key_left })}</>}
    </span>
  );
}

export function liveMoney(o: { source?: string | null; facts?: LiveFacts | null }, value: number, fallback: (n: number) => string) {
  const cur = o.facts?.currency;
  return cur ? `${Number(value).toLocaleString(undefined, { maximumFractionDigits: 0 })} ${cur}` : fallback(value);
}
