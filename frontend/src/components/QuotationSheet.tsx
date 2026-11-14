import { CSSProperties } from "react";
import { useI18n } from "../lang";
import type { ServicePart } from "../types";
import { shortDate } from "../util";
import { moneyText } from "./Money";
import { PART_LABELS } from "./requests/QuotePanel";
import "../styles/quote.css";

export interface QuotationData {
  kind: "draft" | "final"; reference: string; title: string; status: string;
  service_en: string | null; service_ar: string | null; client: string;
  destination: string | null; origin: string | null; depart: string | null; return: string | null; adults: number; children: number;
  items: { part: ServicePart; title: string; provider: string | null; link: string | null; details: string | null;
    image_url: string | null; stars: number | null; price: number | null; chosen: boolean }[];
  currency: string; total: number | null; issued_at: string; valid_until: string;
  company: { name: string; logo: string | null; primary: string; accent: string; email: string | null; phone: string | null; whatsapp: string | null };
  design: { intro_en: string; intro_ar: string; terms_en: string; terms_ar: string; footer_en: string; footer_ar: string; valid_days: number };
}

/** The quotation as one printable page in the company's colours (the browser prints it to PDF). */
export default function QuotationSheet({ q }: { q: QuotationData }) {
  const { t, lang } = useI18n();
  const ar = lang === "ar";
  const pick = (en: string, arText: string) => (ar ? arText || en : en || arText);
  const parts = [...new Set(q.items.map((i) => i.part))];
  const money = (v: number | null) => (v == null ? "—" : moneyText(v, q.currency, lang));
  const travellers = t("{a} adults", { a: q.adults }) + (q.children ? ` · ${t("{c} children", { c: q.children })}` : "");
  return (
    <article className="qt-sheet" style={{ "--qt-brand": q.company.primary, "--qt-accent": q.company.accent } as CSSProperties}>
      <header className="qt-head">
        <div className="qt-brand">
          {q.company.logo ? <img src={q.company.logo} alt={q.company.name} className="qt-logo" /> : <strong className="qt-name">{q.company.name}</strong>}
        </div>
        <div className="qt-meta">
          <div className="qt-kind">{q.kind === "final" ? t("Final quotation") : t("Quotation")}</div>
          <div><bdi dir="ltr">{q.reference}</bdi></div>
          <div>{t("Issued {date}", { date: shortDate(q.issued_at) })}</div>
          <div>{t("Valid until {date}", { date: shortDate(q.valid_until) })}</div>
        </div>
      </header>

      <section className="qt-trip">
        <div>
          <div className="qt-label">{t("Prepared for")}</div>
          <div className="qt-big" dir="auto">{q.client || "—"}</div>
        </div>
        <div>
          <div className="qt-label">{pick(q.service_en ?? "", q.service_ar ?? "") || t("Trip")}</div>
          <div className="qt-big" dir="auto">{q.destination || q.title}</div>
          <div className="qt-muted">
            {q.depart ? shortDate(q.depart) : ""}{q.return ? ` – ${shortDate(q.return)}` : ""}{q.depart ? " · " : ""}{travellers}
          </div>
        </div>
      </section>

      {pick(q.design.intro_en, q.design.intro_ar) && <p className="qt-intro" dir="auto">{pick(q.design.intro_en, q.design.intro_ar)}</p>}

      {parts.map((p) => (
        <section key={p} className="qt-part">
          <h2>{t(PART_LABELS[p] ?? "Other")}</h2>
          {q.kind === "draft" && q.items.filter((i) => i.part === p).length > 1 && (
            <p className="qt-muted qt-small">{t("Choose one of these options.")}</p>
          )}
          {q.items.filter((i) => i.part === p).map((i, n) => (
            <div key={n} className="qt-item">
              {i.image_url && <img src={i.image_url} alt="" className="qt-photo" />}
              <div className="qt-item-main">
                <div className="qt-item-title" dir="auto">
                  {q.kind === "draft" && <span className="qt-num">{n + 1}</span>}
                  {i.title}{i.stars ? <span className="qt-stars"> {"★".repeat(i.stars)}</span> : null}
                </div>
                {i.provider && i.provider !== i.title && <div className="qt-muted" dir="auto">{i.provider}</div>}
                {i.details && <p className="qt-details" dir="auto">{i.details}</p>}
                {i.link && <div className="qt-link" dir="ltr">{i.link.replace(/^https?:\/\//, "").slice(0, 70)}</div>}
              </div>
              <div className="qt-price">{money(i.price)}</div>
            </div>
          ))}
        </section>
      ))}

      {q.kind === "final" && q.total != null && (
        <div className="qt-total"><span>{t("Total")}</span><strong>{money(q.total)}</strong></div>
      )}

      {pick(q.design.terms_en, q.design.terms_ar) && (
        <section className="qt-terms">
          <h2>{t("Terms and conditions")}</h2>
          <p dir="auto">{pick(q.design.terms_en, q.design.terms_ar)}</p>
        </section>
      )}
      <footer className="qt-foot">
        {pick(q.design.footer_en, q.design.footer_ar) && <div dir="auto">{pick(q.design.footer_en, q.design.footer_ar)}</div>}
        <div className="qt-contacts">
          <strong>{q.company.name}</strong>
          {q.company.phone && <bdi dir="ltr">{q.company.phone}</bdi>}
          {q.company.whatsapp && q.company.whatsapp !== q.company.phone && <bdi dir="ltr">WhatsApp {q.company.whatsapp}</bdi>}
          {q.company.email && <bdi dir="ltr">{q.company.email}</bdi>}
        </div>
      </footer>
    </article>
  );
}
