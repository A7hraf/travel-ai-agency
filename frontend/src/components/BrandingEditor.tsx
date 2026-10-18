import { CSSProperties, FormEvent, ReactNode, useEffect, useState } from "react";
import { get, patch } from "../api";
import { useI18n } from "../lang";
import { dashboardVars, isDark, storefrontVars } from "../theme";
import { GhanjahMark } from "./Brand";
import type { Branding, PublicCompany, Section } from "../types";
import ImageUpload from "./ImageUpload";
import { Switch } from "./admin/AdminUI";
import { ArrowDown, ArrowSquareOut, ArrowUp, Check, ChatCircleDots, MagnifyingGlass, PaintBrush, Phone, Rows, SquaresFour, WhatsappLogo } from "./Icon";
import { Money } from "./Money";
import { Poster } from "./Poster";
import { ErrorBox, Field } from "./ui";

const ALL_SECTIONS: Section[] = ["search", "featured", "offers", "about", "contact"];

const SECTION_LABELS: Record<Section, string> = {
  search: "Search bar",
  featured: "Featured packages",
  offers: "All offers",
  about: "About us",
  contact: "Contact & WhatsApp",
};

/** Ready themes of the design (ghanjah-data.js THEMES): main and accent colour. */
const THEMES: { name: string; p: string; a: string }[] = [
  { name: "Ghanjah", p: "#0088b0", a: "#4fb6dc" },
  { name: "Ocean", p: "#1f5fa8", a: "#5fb3e6" },
  { name: "Desert", p: "#a8641f", a: "#e3b26b" },
  { name: "Royal", p: "#4b3a8f", a: "#c9a54b" },
  { name: "Oasis", p: "#2e7d5b", a: "#9bcb6b" },
  { name: "Rose", p: "#b23a6b", a: "#f2a1bd" },
  { name: "Night", p: "#2b3a55", a: "#7fa7d9" },
];

const HEX = /^#[0-9a-fA-F]{6}$/;

/** Default customer-page hero of the design: "Where to *next?*". */
const HERO_DEFAULT = { en: ["Where to", "next?"], ar: ["وين وجهتك", "الجاية؟"] };

interface PreviewPackage { id: number; title: string; destination: string; country: string; duration_days: number;
  price_per_person: number; currency: string; image_url: string | null; is_featured: boolean }

/** Shown in the preview when the company has no packages yet (or its page is offline). */
const SAMPLE: PreviewPackage[] = [
  { id: -1, title: "Maldives", destination: "Maldives", country: "Maldives", duration_days: 6, price_per_person: 0, currency: "", image_url: null, is_featured: true },
  { id: -2, title: "Istanbul", destination: "Istanbul", country: "Türkiye", duration_days: 8, price_per_person: 0, currency: "", image_url: null, is_featured: true },
  { id: -3, title: "Salalah", destination: "Salalah", country: "Oman", duration_days: 3, price_per_person: 0, currency: "", image_url: null, is_featured: false },
  { id: -4, title: "Dubai", destination: "Dubai", country: "UAE", duration_days: 4, price_per_person: 0, currency: "", image_url: null, is_featured: false },
];

function ColorInput({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  const { t } = useI18n();
  const [text, setText] = useState(value);
  useEffect(() => setText(value), [value]);
  const invalid = !HEX.test(text);
  return (
    <Field label={label} hint={invalid
      ? <span className="error-text" role="alert">{t("Not a valid colour. Use # and 6 characters 0-9 / a-f, for example #0088b0. The last valid colour is kept.")}</span>
      : undefined}>
      <div className={`color-input ${invalid ? "invalid" : ""}`}>
        <span className="color-swatch" style={{ background: value }}>
          <input type="color" value={value} onChange={(e) => onChange(e.target.value)} aria-label={label} />
        </span>
        <input value={text} maxLength={7} dir="ltr" aria-invalid={invalid} aria-label={`${label} (hex)`} spellCheck={false} onChange={(e) => {
          setText(e.target.value);
          if (HEX.test(e.target.value)) onChange(e.target.value.toLowerCase());
        }} onBlur={() => { if (!HEX.test(text)) setText(value); }} />
      </div>
    </Field>
  );
}

function Seg<T extends string>({ value, options, onChange, label }: {
  value: T; options: { v: T; label: string; icon?: ReactNode }[]; onChange: (v: T) => void; label: string;
}) {
  return (
    <div className="seg" role="group" aria-label={label}>
      {options.map((o) => (
        <button type="button" key={o.v} className={value === o.v ? "active" : ""} aria-pressed={value === o.v} onClick={() => onChange(o.v)}>
          {o.icon}{o.label}
        </button>
      ))}
    </div>
  );
}

/** Edits a company's customer page (and, for the platform owner, the employee dashboard colours). */
export default function BrandingEditor({ loadPath, uploadPath, slug, owner, onSaved, name }: {
  loadPath: string;
  uploadPath: string;
  slug: string;
  owner?: boolean;
  onSaved?: () => void;
  /** Company name for the preview (else read from the public page). */
  name?: string;
}) {
  const { t, lang } = useI18n();
  const [b, setB] = useState<Branding | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [saving, setSaving] = useState(false);
  const [info, setInfo] = useState<PublicCompany | null>(null);
  const [pkgs, setPkgs] = useState<PreviewPackage[]>([]);

  useEffect(() => { get<Branding>(loadPath).then(setB).catch((e) => setError(e.message)); }, [loadPath]);
  useEffect(() => {
    // Real content for the preview, from the public page (suspended companies have none: samples are used).
    get<PublicCompany>(`/api/public/companies/${slug}`).then(setInfo).catch(() => {});
    get<PreviewPackage[]>(`/api/public/companies/${slug}/packages`).then(setPkgs).catch(() => {});
  }, [slug]);
  if (!b) return error ? <ErrorBox error={error} /> : <div className="skeleton" style={{ height: 420, borderRadius: 24 }} />;

  const set = <K extends keyof Branding>(k: K, v: Branding[K]) => { setSaved(false); setB({ ...b, [k]: v }); };
  // The search bar is always at the top of the page: it can be turned on/off but not moved.
  const searchOn = b.sections.includes("search");
  const movable: Section[] = ALL_SECTIONS.filter((s) => s !== "search");
  const order: Section[] = [...b.sections.filter((s) => s !== "search"), ...movable.filter((s) => !b.sections.includes(s))];
  const withSearch = (list: Section[], on = searchOn): Section[] => (on ? ["search", ...list] : list);
  const toggle = (s: Section) => {
    if (s === "search") {
      set("sections", withSearch(b.sections.filter((x) => x !== "search"), !searchOn));
      return;
    }
    set("sections", withSearch(b.sections.includes(s)
      ? order.filter((x) => x !== s && b.sections.includes(x))
      : order.filter((x) => x === s || b.sections.includes(x))));
  };
  const move = (s: Section, step: number) => {
    const list = [...order];
    const i = list.indexOf(s);
    const j = i + step;
    if (j < 0 || j >= list.length) return;
    [list[i], list[j]] = [list[j], list[i]];
    set("sections", withSearch(list.filter((x) => b.sections.includes(x))));
  };

  const save = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setSaving(true);
    try {
      const body: Partial<Branding> = { ...b };
      if (!owner) {
        delete body.dashboard_color;
        delete body.dashboard_sidebar;
      }
      setB(await patch<Branding>(loadPath, body));
      setSaved(true);
      onSaved?.();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const activeTheme = THEMES.find((x) => x.p === b.primary_color.toLowerCase() && x.a === b.accent_color.toLowerCase());

  return (
    <form className="bz" onSubmit={save}>
      <div className="bz-form">
        <section className="ad-card">
          <h2 className="ad-card-title"><span className="ad-card-icon"><PaintBrush /></span>{t("Colours")}</h2>
          <div className="ad-section-label">{t("Ready themes")}</div>
          <div className="bz-themes">
            {THEMES.map((p) => {
              const on = activeTheme?.name === p.name;
              return (
                <button type="button" key={p.name} className={`bz-theme ${on ? "active" : ""}`} aria-pressed={on} onClick={() => {
                  setSaved(false);
                  setB({ ...b, primary_color: p.p, accent_color: p.a, ...(owner ? { dashboard_color: p.p } : {}) });
                }}>
                  <span className="bz-theme-dots"><i style={{ background: p.p }} /><i style={{ background: p.a }} /></span>
                  {t(p.name)}
                  {on && <Check weight="bold" className="bz-theme-check" />}
                </button>
              );
            })}
          </div>
          <div className="ad-grid-2">
            <ColorInput label={t("Main colour")} value={b.primary_color} onChange={(v) => set("primary_color", v)} />
            <ColorInput label={t("Accent colour")} value={b.accent_color} onChange={(v) => set("accent_color", v)} />
          </div>
          <div className="field">
            <span className="field-label">{t("Logo")}</span>
            <ImageUpload value={b.logo} onChange={(url) => set("logo", url)} endpoint={uploadPath} maxSide={512} contain />
            <span className="field-hint">{t("PNG or SVG, square works best.")} {t("Shown on the customer page and in the employee dashboard.")}</span>
          </div>
        </section>

        {owner && (
          <section className="ad-card">
            <h2 className="ad-card-title">{t("Employee dashboard")}</h2>
            <p className="ad-card-note">{t("Only you (the platform owner) can change these. Company employees see them after their next page load.")}</p>
            <div className="ad-grid-2">
              <ColorInput label={t("Dashboard main colour")} value={b.dashboard_color} onChange={(v) => set("dashboard_color", v)} />
              <ColorInput label={t("Sidebar colour")} value={b.dashboard_sidebar} onChange={(v) => set("dashboard_sidebar", v)} />
            </div>
            <button type="button" className="btn btn-sm btn-soft" onClick={() => set("dashboard_color", b.primary_color)}>
              {t("Use the customer page colour")}
            </button>
            <div className="ad-section-label md-label">{t("Staff dashboard preview")}</div>
            <DashboardPreview b={b} name={name ?? info?.name ?? ""} />
          </section>
        )}

        <section className="ad-card">
          <h2 className="ad-card-title">{t("Top banner")}</h2>
          <div className="field">
            <span className="field-label">{t("Style")}</span>
            <Seg label={t("Style")} value={b.hero_style} onChange={(v) => set("hero_style", v)} options={[
              { v: "gradient", label: t("Gradient") }, { v: "solid", label: t("Solid colour") }, { v: "image", label: t("Photo") }]} />
          </div>
          {b.hero_style === "image" && (
            <div className="field">
              <span className="field-label">{t("Banner photo")}</span>
              <ImageUpload value={b.hero_image} onChange={(url) => set("hero_image", url)} endpoint={uploadPath} maxSide={1920} />
            </div>
          )}
          <div className="ad-grid-2">
            <Field label={t("Title (English)")}><input value={b.hero_title_en} maxLength={120} dir="ltr" placeholder="Where to next?" onChange={(e) => set("hero_title_en", e.target.value)} /></Field>
            <Field label={t("Title (Arabic)")}><input value={b.hero_title_ar} maxLength={120} dir="rtl" placeholder="وين وجهتك الجاية؟" onChange={(e) => set("hero_title_ar", e.target.value)} /></Field>
            <Field label={t("Text (English)")}><textarea rows={3} value={b.hero_text_en} maxLength={400} dir="ltr" onChange={(e) => set("hero_text_en", e.target.value)} /></Field>
            <Field label={t("Text (Arabic)")}><textarea rows={3} value={b.hero_text_ar} maxLength={400} dir="rtl" onChange={(e) => set("hero_text_ar", e.target.value)} /></Field>
          </div>
          <p className="field-hint">{t("Leave empty to use the standard text. The last word of the title is highlighted.")}</p>
        </section>

        <section className="ad-card">
          <h2 className="ad-card-title">{t("Page structure")}</h2>
          <p className="ad-card-note">{t("Choose which parts appear on the customer page and in which order.")}</p>
          <ul className="bz-sections">
            <li className={searchOn ? "" : "off"}>
              <Switch checked={searchOn} onChange={() => toggle("search")} label={t(SECTION_LABELS.search)} hint={t("The search bar is always at the top.")} />
            </li>
            {order.map((s, i) => (
              <li key={s} className={b.sections.includes(s) ? "" : "off"}>
                <Switch checked={b.sections.includes(s)} onChange={() => toggle(s)} label={t(SECTION_LABELS[s])} />
                <span className="spacer" />
                <button type="button" className="icon-btn" disabled={i === 0} onClick={() => move(s, -1)} aria-label={`${t("Move up")}: ${t(SECTION_LABELS[s])}`}><ArrowUp /></button>
                <button type="button" className="icon-btn" disabled={i === order.length - 1} onClick={() => move(s, 1)} aria-label={`${t("Move down")}: ${t(SECTION_LABELS[s])}`}><ArrowDown /></button>
              </li>
            ))}
          </ul>
        </section>

        <section className="ad-card">
          <h2 className="ad-card-title">{t("Packages and cards")}</h2>
          <div className="ad-grid-2">
            <div className="field">
              <span className="field-label">{t("Package layout")}</span>
              <Seg label={t("Package layout")} value={b.layout} onChange={(v) => set("layout", v)} options={[
                { v: "grid", label: t("Cards grid"), icon: <SquaresFour /> }, { v: "list", label: t("List"), icon: <Rows /> }]} />
            </div>
            <div className="field">
              <span className="field-label">{t("Card corners")}</span>
              <Seg label={t("Card corners")} value={b.card_style} onChange={(v) => set("card_style", v)} options={[
                { v: "rounded", label: t("Rounded") }, { v: "square", label: t("Square") }]} />
            </div>
          </div>
        </section>

        <section className="ad-card">
          <h2 className="ad-card-title">{t("About us")}</h2>
          <div className="ad-grid-2">
            <Field label={t("Title (English)")}><input value={b.about_title_en} maxLength={120} dir="ltr" placeholder="About us" onChange={(e) => set("about_title_en", e.target.value)} /></Field>
            <Field label={t("Title (Arabic)")}><input value={b.about_title_ar} maxLength={120} dir="rtl" placeholder="من نحن" onChange={(e) => set("about_title_ar", e.target.value)} /></Field>
            <Field label={t("Text (English)")}><textarea rows={5} value={b.about_en} maxLength={3000} dir="ltr" onChange={(e) => set("about_en", e.target.value)} /></Field>
            <Field label={t("Text (Arabic)")}><textarea rows={5} value={b.about_ar} maxLength={3000} dir="rtl" onChange={(e) => set("about_ar", e.target.value)} /></Field>
          </div>
        </section>

        <div className="bz-bar">
          <div className="bz-bar-msg" aria-live="polite">
            <ErrorBox error={error} />
            {saved && <div className="ok-box ad-notice">{t("Saved. Customers see the new design right away.")}</div>}
          </div>
          <a className="btn btn-ghost" href={`/c/${slug}`} target="_blank" rel="noreferrer"><ArrowSquareOut />{t("Open customer page")}</a>
          <button className="btn btn-primary" disabled={saving} aria-busy={saving}>{saving ? t("Saving…") : t("Save design")}</button>
        </div>
      </div>

      <aside className="bz-preview" aria-label={t("Live preview")}>
        <div className="bz-preview-label"><span className="live-dot" aria-hidden="true" />{t("Live preview")}</div>
        <MiniPage b={b} name={name ?? info?.name ?? ""} agent={info?.ai_agent_name ?? "Sara"} whatsapp={info?.whatsapp_number ?? null}
          phone={info?.contact_phone ?? null} pkgs={pkgs.length ? pkgs : SAMPLE} lang={lang} />
      </aside>
    </form>
  );
}

/** The customer page in miniature: dark surface, the agency colours as accents, posters, hero with an accent word. */
function MiniPage({ b, name, agent, whatsapp, phone, pkgs, lang }: {
  b: Branding; name: string; agent: string; whatsapp: string | null; phone: string | null; pkgs: PreviewPackage[]; lang: "en" | "ar";
}) {
  const { t } = useI18n();
  const custom = (lang === "ar" ? b.hero_title_ar : b.hero_title_en).trim();
  const words = custom ? custom.split(/\s+/) : [];
  const [head, accent] = custom
    ? [words.slice(0, -1).join(" "), words[words.length - 1]]
    : HERO_DEFAULT[lang];
  const text = (lang === "ar" ? b.hero_text_ar : b.hero_text_en)
    || t("Browse our packages or chat with our AI travel consultant.");
  const about = (lang === "ar" ? b.about_ar : b.about_en);
  const aboutTitle = (lang === "ar" ? b.about_title_ar : b.about_title_en) || t("About us");
  const featured = pkgs.filter((p) => p.is_featured).slice(0, 3);
  const radius = b.card_style === "square" ? 4 : 14;
  const heroStyle: CSSProperties = b.hero_style === "image" && b.hero_image
    ? { backgroundImage: `linear-gradient(180deg, rgba(20,19,18,.35), rgba(32,30,29,.95)), url(${JSON.stringify(b.hero_image)})` }
    : {};
  const poster = (p: PreviewPackage, cls: string) => (
    <Poster key={p.id} destination={p.destination} country={p.country} title={p.title} imageUrl={p.image_url}
      className={`mp-poster ${cls}`} style={{ ["--poster-radius" as string]: `${radius}px` }} stamp={false}>
      <div className="poster-body">
        <div className="poster-country">{p.country}</div>
        <div className="poster-name" dir="auto">{p.destination}</div>
        {p.currency && <div className="poster-foot"><span>{p.duration_days}d</span><Money value={p.price_per_person} currency={p.currency} lang={lang} /></div>}
      </div>
    </Poster>
  );

  return (
    <div className="mp" dir={lang === "ar" ? "rtl" : "ltr"} style={storefrontVars(b.primary_color, b.accent_color) as CSSProperties} aria-hidden="true">
      <div className={`mp-hero mp-hero-${b.hero_style}`} style={heroStyle}>
        <div className="mp-nav">
          {b.logo ? <img src={b.logo} alt="" className="mp-logo-img" /> : <span className="mp-logo"><span /></span>}
          <span className="mp-name" dir="auto">{name}</span>
          <span className="mp-lang">{lang === "ar" ? "English" : "العربية"}</span>
          <span className="mp-chat"><ChatCircleDots weight="fill" /></span>
        </div>
        <div className="mp-kicker"><i />{lang === "ar" ? `${agent} متصلة الآن` : `${agent} is online`}</div>
        <div className="mp-title" dir="auto">{head} <em>{accent}</em></div>
        <p className="mp-text" dir="auto">{text}</p>
        {b.sections.includes("search") && (
          <div className="mp-search"><MagnifyingGlass /><span>{lang === "ar" ? "الوجهة أو نوع الرحلة" : "Destination or trip type"}</span></div>
        )}
      </div>
      <div className="mp-body">
        {b.sections.filter((s) => s !== "search").map((s) => (
          <div key={s} className="mp-section">
            {s === "featured" && featured.length > 0 && (<>
              <div className="mp-h">{lang === "ar" ? "رحلات مميّزة" : "Featured trips"}</div>
              <div className="mp-row">{featured.map((p) => poster(p, "tall"))}</div>
            </>)}
            {s === "offers" && (<>
              <div className="mp-h">{lang === "ar" ? "عروضنا" : "Our offers"}<small>{pkgs.length}</small></div>
              {b.layout === "grid" ? (
                <div className="mp-grid">{pkgs.slice(0, 4).map((p) => poster(p, "grid"))}</div>
              ) : (
                <div className="mp-list">
                  {pkgs.slice(0, 3).map((p) => (
                    <div key={p.id} className="mp-item">
                      <Poster destination={p.destination} country={p.country} title={p.title} imageUrl={p.image_url} stamp={false} route={false}
                        className="mp-thumb" style={{ ["--poster-radius" as string]: `${Math.min(radius, 10)}px` }} />
                      <div className="mp-item-text"><small>{p.country}</small><b dir="auto">{p.title}</b></div>
                      <span className="mp-book">{lang === "ar" ? "احجز" : "Book"}</span>
                    </div>
                  ))}
                </div>
              )}
            </>)}
            {s === "about" && (<>
              <div className="mp-h" dir="auto">{aboutTitle}</div>
              <p className="mp-about" dir="auto">{about ? about.slice(0, 140) : "…"}</p>
            </>)}
            {s === "contact" && (
              <div className="mp-contact">
                <span className="wa"><WhatsappLogo weight="fill" />{lang === "ar" ? "واتساب" : "WhatsApp"}</span>
                {(phone || whatsapp) && <span><Phone /><bdi dir="ltr">{phone || whatsapp}</bdi></span>}
              </div>
            )}
          </div>
        ))}
      </div>
      <div className="mp-dock"><span className="mp-dock-av">{agent.slice(0, 1)}</span>{lang === "ar" ? `تحدّث مع ${agent}` : `Chat with ${agent}`}</div>
    </div>
  );
}

/** Staff dashboard in miniature, in the dark shell style with the chosen sidebar and main colour. */
function DashboardPreview({ b, name }: { b: Branding; name: string }) {
  return (
    <div className="md" style={dashboardVars(b.dashboard_color, b.dashboard_sidebar) as CSSProperties} aria-hidden="true">
      <div className="md-side">
        <div className="md-brand">
          {b.logo ? <img src={b.logo} alt="" /> : <GhanjahMark dark={isDark(b.dashboard_sidebar)} />}
          <span>{name}</span>
        </div>
        <i className="on" /><i /><i /><i /><i />
        <span className="md-user" />
      </div>
      <div className="md-main">
        <span className="md-hello" />
        <div className="md-kpis"><i className="hero" /><i /><i /><i /></div>
        <div className="md-chart">{[40, 65, 50, 80, 60, 90, 75, 55, 85, 70].map((h, i) => (
          <i key={i} style={{ height: `${h}%` }}><b style={{ height: `${30 + (i % 3) * 10}%` }} /></i>
        ))}</div>
        <span className="md-btn" />
      </div>
    </div>
  );
}
