import { CSSProperties, FormEvent, useEffect, useState } from "react";
import { get, patch } from "../api";
import { useI18n } from "../lang";
import { dashboardVars, storefrontVars } from "../theme";
import type { Branding, Section } from "../types";
import ImageUpload from "./ImageUpload";
import { STOREFRONT_TEXT } from "../i18n";
import { ErrorBox, Field } from "./ui";

const ALL_SECTIONS: Section[] = ["search", "featured", "offers", "about", "contact"];

const SECTION_LABELS: Record<Section, string> = {
  search: "Search bar",
  featured: "Featured packages",
  offers: "All offers",
  about: "About us",
  contact: "Contact & WhatsApp",
};

const PRESETS: { name: string; primary: string; accent: string; sidebar: string }[] = [
  { name: "Ocean", primary: "#0e7490", accent: "#22d3ee", sidebar: "#0b1f2a" },
  { name: "Desert", primary: "#b45309", accent: "#fbbf24", sidebar: "#2b1a0e" },
  { name: "Royal", primary: "#4338ca", accent: "#a78bfa", sidebar: "#1e1b4b" },
  { name: "Oasis", primary: "#047857", accent: "#6ee7b7", sidebar: "#052e2b" },
  { name: "Rose", primary: "#be123c", accent: "#fda4af", sidebar: "#2a0a14" },
  { name: "Night", primary: "#1f2937", accent: "#f59e0b", sidebar: "#0b0f17" },
];

const HEX = /^#[0-9a-fA-F]{6}$/;

function ColorInput({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  const { t } = useI18n();
  const [text, setText] = useState(value);
  useEffect(() => setText(value), [value]);
  const invalid = !HEX.test(text);
  return (
    <Field label={label} hint={invalid
      ? <span className="error-text">{t("Not a valid colour. Use # and 6 characters 0-9 / a-f, for example #0e7490. The last valid colour is kept.")}</span>
      : undefined}>
      <div className="color-input">
        <input type="color" value={value} onChange={(e) => onChange(e.target.value)} aria-label={label} />
        <input value={text} maxLength={7} dir="ltr" aria-invalid={invalid} aria-label={`${label} (hex)`} onChange={(e) => {
          setText(e.target.value);
          if (HEX.test(e.target.value)) onChange(e.target.value.toLowerCase());
        }} onBlur={() => { if (!HEX.test(text)) setText(value); }} />
      </div>
    </Field>
  );
}

/** Edits a company's customer page (and, for the platform owner, the employee dashboard colours). */
export default function BrandingEditor({ loadPath, uploadPath, slug, owner, onSaved }: {
  loadPath: string;
  uploadPath: string;
  slug: string;
  owner?: boolean;
  onSaved?: () => void;
}) {
  const { t, lang } = useI18n();
  const [b, setB] = useState<Branding | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => { get<Branding>(loadPath).then(setB).catch((e) => setError(e.message)); }, [loadPath]);
  if (!b) return error ? <ErrorBox error={error} /> : <div className="loading">{t("Loading…")}</div>;

  const set = <K extends keyof Branding>(k: K, v: Branding[K]) => { setSaved(false); setB({ ...b, [k]: v }); };
  // The search bar is always at the top of the page: it can be turned on/off but not moved.
  const searchOn = b.sections.includes("search");
  const movable = ALL_SECTIONS.filter((s) => s !== "search");
  const order = [...b.sections.filter((s) => s !== "search"), ...movable.filter((s) => !b.sections.includes(s))];
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

  // The same default title customers see.
  const title = (lang === "ar" ? b.hero_title_ar : b.hero_title_en) || STOREFRONT_TEXT[lang].heroTitle;
  const text = (lang === "ar" ? b.hero_text_ar : b.hero_text_en) || t("Browse our packages or chat with our AI travel consultant.");

  return (
    <form className="branding" onSubmit={save}>
      <div className="branding-form">
        <section className="card">
          <h3>{t("Colours")}</h3>
          <div className="presets">
            {PRESETS.map((p) => (
              <button type="button" key={p.name} className="preset" title={t(p.name)} onClick={() => {
                setSaved(false);
                setB({ ...b, primary_color: p.primary, accent_color: p.accent,
                  ...(owner ? { dashboard_color: p.primary, dashboard_sidebar: p.sidebar } : {}) });
              }}>
                <span style={{ background: p.primary }} /><span style={{ background: p.accent }} /><span style={{ background: p.sidebar }} />
                <em>{t(p.name)}</em>
              </button>
            ))}
          </div>
          <div className="form-grid">
            <ColorInput label={t("Main colour")} value={b.primary_color} onChange={(v) => set("primary_color", v)} />
            <ColorInput label={t("Accent colour")} value={b.accent_color} onChange={(v) => set("accent_color", v)} />
          </div>
          <Field label={t("Logo")} hint={t("Shown on the customer page and in the employee dashboard. A square logo with a transparent background looks best.")}>
            <ImageUpload value={b.logo} onChange={(url) => set("logo", url)} endpoint={uploadPath} maxSide={512} contain />
          </Field>
        </section>

        {owner && (
          <section className="card">
            <h3>{t("Employee dashboard")}</h3>
            <p className="muted small">{t("Only you (the platform owner) can change these. Company employees see them after their next page load.")}</p>
            <div className="form-grid">
              <ColorInput label={t("Dashboard main colour")} value={b.dashboard_color} onChange={(v) => set("dashboard_color", v)} />
              <ColorInput label={t("Sidebar colour")} value={b.dashboard_sidebar} onChange={(v) => set("dashboard_sidebar", v)} />
            </div>
            <button type="button" className="btn btn-sm" onClick={() => setB({ ...b, dashboard_color: b.primary_color })}>
              {t("Use the customer page colour")}
            </button>
            <DashboardPreview b={b} />
          </section>
        )}

        <section className="card">
          <h3>{t("Top banner")}</h3>
          <Field label={t("Banner style")}>
            <div className="seg">
              {(["gradient", "solid", "image"] as const).map((s) => (
                <button type="button" key={s} className={b.hero_style === s ? "active" : ""} onClick={() => set("hero_style", s)}>
                  {t({ gradient: "Gradient", solid: "Solid colour", image: "Photo" }[s])}
                </button>
              ))}
            </div>
          </Field>
          {b.hero_style === "image" && (
            <Field label={t("Banner photo")}>
              <ImageUpload value={b.hero_image} onChange={(url) => set("hero_image", url)} endpoint={uploadPath} maxSide={1920} />
            </Field>
          )}
          <div className="form-grid">
            <Field label={t("Title (English)")}><input value={b.hero_title_en} maxLength={120} dir="ltr" placeholder="Where do you want to go next?" onChange={(e) => set("hero_title_en", e.target.value)} /></Field>
            <Field label={t("Title (Arabic)")}><input value={b.hero_title_ar} maxLength={120} dir="rtl" placeholder="وين وجهتك الجاية؟" onChange={(e) => set("hero_title_ar", e.target.value)} /></Field>
            <Field label={t("Text (English)")}><textarea rows={3} value={b.hero_text_en} maxLength={400} dir="ltr" onChange={(e) => set("hero_text_en", e.target.value)} /></Field>
            <Field label={t("Text (Arabic)")}><textarea rows={3} value={b.hero_text_ar} maxLength={400} dir="rtl" onChange={(e) => set("hero_text_ar", e.target.value)} /></Field>
          </div>
          <p className="field-hint">{t("Leave empty to use the standard text.")}</p>
        </section>

        <section className="card">
          <h3>{t("Page structure")}</h3>
          <p className="muted small">{t("Choose which parts appear on the customer page and in which order.")}</p>
          <div className="section-list">
            <div className={`section-row ${searchOn ? "" : "off"}`}>
              <label className="check"><input type="checkbox" checked={searchOn} onChange={() => toggle("search")} /> {t(SECTION_LABELS.search)}</label>
              <span className="spacer" />
              <span className="muted small">{t("Always at the top")}</span>
            </div>
            {order.map((s, i) => (
              <div key={s} className={`section-row ${b.sections.includes(s) ? "" : "off"}`}>
                <label className="check"><input type="checkbox" checked={b.sections.includes(s)} onChange={() => toggle(s)} /> {t(SECTION_LABELS[s])}</label>
                <span className="spacer" />
                <button type="button" className="icon-btn" disabled={i === 0} onClick={() => move(s, -1)} aria-label={t("Move up")}>↑</button>
                <button type="button" className="icon-btn" disabled={i === order.length - 1} onClick={() => move(s, 1)} aria-label={t("Move down")}>↓</button>
              </div>
            ))}
          </div>
          <div className="form-grid">
            <Field label={t("Package layout")}>
              <div className="seg">
                {(["grid", "list"] as const).map((s) => (
                  <button type="button" key={s} className={b.layout === s ? "active" : ""} onClick={() => set("layout", s)}>
                    {t(s === "grid" ? "Cards grid" : "List")}
                  </button>
                ))}
              </div>
            </Field>
            <Field label={t("Card corners")}>
              <div className="seg">
                {(["rounded", "square"] as const).map((s) => (
                  <button type="button" key={s} className={b.card_style === s ? "active" : ""} onClick={() => set("card_style", s)}>
                    {t(s === "rounded" ? "Rounded" : "Square")}
                  </button>
                ))}
              </div>
            </Field>
          </div>
        </section>

        <section className="card">
          <h3>{t("About us")}</h3>
          <div className="form-grid">
            <Field label={t("Title (English)")}><input value={b.about_title_en} maxLength={120} dir="ltr" placeholder="About us" onChange={(e) => set("about_title_en", e.target.value)} /></Field>
            <Field label={t("Title (Arabic)")}><input value={b.about_title_ar} maxLength={120} dir="rtl" placeholder="من نحن" onChange={(e) => set("about_title_ar", e.target.value)} /></Field>
            <Field label={t("Text (English)")}><textarea rows={5} value={b.about_en} maxLength={3000} dir="ltr" onChange={(e) => set("about_en", e.target.value)} /></Field>
            <Field label={t("Text (Arabic)")}><textarea rows={5} value={b.about_ar} maxLength={3000} dir="rtl" onChange={(e) => set("about_ar", e.target.value)} /></Field>
          </div>
        </section>

        <ErrorBox error={error} />
        {saved && <div className="ok-box">{t("Saved. Customers see the new design right away.")}</div>}
        <div className="branding-actions">
          <a className="btn" href={`/c/${slug}`} target="_blank" rel="noreferrer">↗ {t("Open customer page")}</a>
          <button className="btn btn-primary" disabled={saving}>{saving ? t("Saving…") : t("Save design")}</button>
        </div>
      </div>

      <aside className="branding-preview">
        <div className="preview-label">{t("Live preview")}</div>
        <div className="mini-sf" style={storefrontVars(b.primary_color, b.accent_color) as CSSProperties}>
          <div className={`mini-hero hero-${b.hero_style}`}
            style={b.hero_style === "image" && b.hero_image ? { backgroundImage: `linear-gradient(rgb(0 0 0 / 35%), rgb(0 0 0 / 55%)), url(${JSON.stringify(b.hero_image)})` } : undefined}>
            <div className="mini-nav">
              {b.logo ? <img src={b.logo} alt="" /> : <span>✈</span>}
              <span className="mini-dot" />
            </div>
            <strong>{title}</strong>
            <small>{text}</small>
            {b.sections.includes("search") && <div className="mini-search"><span /><button type="button" tabIndex={-1}>{t("Chat")}</button></div>}
          </div>
          <div className="mini-body">
            {b.sections.filter((s) => s !== "search").map((s) => (
              <div key={s} className="mini-section">
                <div className="mini-title">{t(SECTION_LABELS[s])}</div>
                {(s === "offers" || s === "featured") && (
                  <div className={`mini-cards ${b.layout}`}>
                    {[0, 1, s === "offers" ? 2 : -1].filter((x) => x >= 0).map((x) => (
                      <div key={x} className={`mini-card ${b.card_style}`}><div /><span /><em /></div>
                    ))}
                  </div>
                )}
                {s === "about" && <p>{(lang === "ar" ? b.about_ar : b.about_en).slice(0, 120) || "…"}</p>}
                {s === "contact" && <div className="mini-contact"><span /><span /></div>}
              </div>
            ))}
          </div>
        </div>
      </aside>
    </form>
  );
}

function DashboardPreview({ b }: { b: Branding }) {
  return (
    <div className="mini-dash" style={dashboardVars(b.dashboard_color, b.dashboard_sidebar) as CSSProperties}>
      <div className="mini-dash-side">
        {b.logo ? <img src={b.logo} alt="" /> : <span className="brand-mark">✈</span>}
        <i className="on" /><i /><i /><i />
      </div>
      <div className="mini-dash-main">
        <div className="mini-dash-tiles"><i /><i /><i /></div>
        <div className="mini-dash-chart">{[40, 65, 50, 80, 60, 90, 75].map((h, i) => <i key={i} style={{ height: `${h}%` }} />)}</div>
        <span className="mini-dash-btn" />
      </div>
    </div>
  );
}
