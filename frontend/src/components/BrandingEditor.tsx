import { CSSProperties, FormEvent, MouseEvent, ReactNode, useEffect, useMemo, useRef, useState } from "react";
import { get, patch } from "../api";
import { useI18n } from "../lang";
import { dashboardVars, isDark } from "../theme";
import { GhanjahMark } from "./Brand";
import type { Branding, CardDesign, PageElements, PublicCompany, Section, TravelPackage } from "../types";
import type { Lang } from "./Money";
import ImageUpload from "./ImageUpload";
import { Switch } from "./admin/AdminUI";
import {
  ArrowCounterClockwise, ArrowDown, ArrowSquareOut, ArrowUp, Cards, Check, DeviceMobile, Images, MagnifyingGlass,
  Monitor, PaintBrush, Rows, SquaresFour, SquaresFour as Layout, TextT, UserGear, Warning, X,
} from "./Icon";
import { StorefrontPage } from "../pages/Storefront";
import { DEFAULT_CARDS, DEFAULT_ELEMENTS, contrastRatio, pageVars } from "./storefront/style";
import { TEXT_GROUPS, defaultText, type TextField } from "./storefront/texts";
import { ErrorBox, Field } from "./ui";

const ALL_SECTIONS: Section[] = ["search", "featured", "offers", "how", "about", "contact"];

const SECTION_LABELS: Record<Section, string> = {
  search: "Search bar",
  featured: "Featured packages",
  offers: "All offers",
  how: "How booking works",
  about: "About us",
  contact: "Contact & WhatsApp",
};

/** Smaller parts of the page, in the order they appear. */
const ELEMENT_LABELS: { key: keyof PageElements; label: string; hint?: string }[] = [
  { key: "kicker", label: "Small line above the title" },
  { key: "lang_switch", label: "Language button (English / العربية)" },
  { key: "whatsapp_icon", label: "WhatsApp icon in the top bar", hint: "Phone" },
  { key: "nav_links", label: "Menu links (Trips, How it works, About)", hint: "Computer" },
  { key: "nav_phone", label: "Phone number in the top bar", hint: "Computer" },
  { key: "budget_filter", label: "Budget filter" },
  { key: "trust", label: "Trust points under the search", hint: "Computer" },
  { key: "hero_chat", label: "Live chat card next to the title", hint: "Computer" },
  { key: "chips", label: "Trip-type chips (All, Honeymoon, Family…)" },
  { key: "offers_count", label: "Number of trips next to \"Our offers\"", hint: "Phone" },
  { key: "prices_note", label: "Note under the prices" },
  { key: "chat_launcher", label: "Chat button at the bottom of the screen" },
  { key: "footer_note", label: "Footer sentence" },
  { key: "powered_by", label: "\"Powered by Ghanjah\"" },
];

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
const STD = { bg: "#201e1d", text: "#f3f2f2" };

/** The standard design (what "Reset all to default" goes back to). Logo and dashboard colours are kept. */
const DEFAULTS: Omit<Branding, "logo" | "dashboard_color" | "dashboard_sidebar"> = {
  primary_color: "#0088b0", accent_color: "#4fb6dc", bg_color: null, surface_color: null, text_color: null,
  highlight_color: null, hero_style: "gradient", hero_image: null,
  hero_title_en: "", hero_title_ar: "", hero_text_en: "", hero_text_ar: "",
  about_title_en: "", about_title_ar: "", about_en: "", about_ar: "",
  about_image: null, about_bg_image: null, how_bg_image: null,
  sections: [...ALL_SECTIONS], elements: { ...DEFAULT_ELEMENTS }, card_style: "rounded", layout: "grid",
  cards: { ...DEFAULT_CARDS }, texts: { en: {}, ar: {} },
};

/** Shown in the preview when the company has no packages yet (or its page is offline). */
const sample = (id: number, title: string, country: string, days: number, price: number, featured: boolean): TravelPackage => ({
  id, title, destination: title, country, description: "", duration_days: days, price_per_person: price, child_price: null,
  currency: "OMR", departure_dates: [], includes: [], excludes: [], tags: [], hotel_name: null, hotel_stars: null,
  seats_available: null, image_url: null, is_active: true, is_featured: featured,
});
const SAMPLE: TravelPackage[] = [
  sample(-1, "Maldives", "Maldives", 6, 690, true), sample(-2, "Istanbul", "Türkiye", 8, 420, true),
  sample(-3, "Salalah", "Oman", 3, 120, false), sample(-4, "Dubai", "UAE", 4, 180, false),
];

type Tab = "theme" | "texts" | "layout" | "photos" | "cards" | "dashboard";

function ColorInput({ label, value, onChange, fallback, hint }: {
  label: string; value: string | null; onChange: (v: string | null) => void;
  /** Optional colour: empty = the standard one (shown greyed). */
  fallback?: string; hint?: ReactNode;
}) {
  const { t } = useI18n();
  const shown = value ?? fallback ?? "#000000";
  const [text, setText] = useState(value ?? "");
  useEffect(() => setText(value ?? ""), [value]);
  const invalid = text !== "" && !HEX.test(text);
  return (
    <Field label={label} hint={invalid
      ? <span className="error-text" role="alert">{t("Not a valid colour. Use # and 6 characters 0-9 / a-f, for example #0088b0. The last valid colour is kept.")}</span>
      : hint}>
      <div className={`color-input ${invalid ? "invalid" : ""} ${value ? "" : "pe-std"}`}>
        <span className="color-swatch" style={{ background: shown }}>
          <input type="color" value={shown} onChange={(e) => onChange(e.target.value)} aria-label={label} />
        </span>
        <input value={text} maxLength={7} dir="ltr" aria-invalid={invalid} aria-label={`${label} (hex)`} spellCheck={false}
          placeholder={fallback ? t("Standard") : undefined} onChange={(e) => {
            setText(e.target.value);
            if (HEX.test(e.target.value)) onChange(e.target.value.toLowerCase());
            else if (e.target.value === "" && fallback) onChange(null);
          }} onBlur={() => { if (text !== "" && !HEX.test(text)) setText(value ?? ""); }} />
        {fallback && value && (
          <button type="button" className="icon-btn pe-reset" onClick={() => onChange(null)} aria-label={`${t("Reset to default")}: ${label}`} title={t("Reset to default")}>
            <ArrowCounterClockwise />
          </button>
        )}
      </div>
    </Field>
  );
}

function Seg<T extends string | number>({ value, options, onChange, label }: {
  value: T; options: { v: T; label: string; icon?: ReactNode }[]; onChange: (v: T) => void; label: string;
}) {
  return (
    <div className="seg" role="group" aria-label={label}>
      {options.map((o) => (
        <button type="button" key={String(o.v)} className={value === o.v ? "active" : ""} aria-pressed={value === o.v} onClick={() => onChange(o.v)}>
          {o.icon}{o.label}
        </button>
      ))}
    </div>
  );
}

/** One text of the page: the standard text as placeholder, and a reset button once changed. */
function TextInput({ id, label, value, placeholder, onChange, max, long, lang, hint }: {
  id: string; label: string; value: string; placeholder: string; onChange: (v: string) => void;
  max: number; long?: boolean; lang: Lang; hint?: ReactNode;
}) {
  const { t } = useI18n();
  const dir = lang === "ar" ? "rtl" : "ltr";
  const changed = value.trim() !== "";
  return (
    <div className={`field pe-text ${changed ? "pe-changed" : ""}`}>
      <label className="field-label" htmlFor={id}>{label}{changed && <span className="pe-dot" title={t("Changed")} />}</label>
      <div className="pe-text-row">
        {long
          ? <textarea id={id} rows={3} value={value} maxLength={max} dir={dir} lang={lang} placeholder={placeholder} onChange={(e) => onChange(e.target.value)} />
          : <input id={id} value={value} maxLength={max} dir={dir} lang={lang} placeholder={placeholder} onChange={(e) => onChange(e.target.value)} />}
        <button type="button" className="icon-btn pe-reset" disabled={!changed} onClick={() => onChange("")}
          aria-label={`${t("Reset to default")}: ${label}`} title={t("Reset to default")}><ArrowCounterClockwise /></button>
      </div>
      {hint && <span className="field-hint">{hint}</span>}
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
  const [savedJson, setSavedJson] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [saving, setSaving] = useState(false);
  const [info, setInfo] = useState<PublicCompany | null>(null);
  const [pkgs, setPkgs] = useState<TravelPackage[]>([]);
  const [tab, setTab] = useState<Tab>("theme");
  const [textLang, setTextLang] = useState<Lang>(lang);
  const [previewLang, setPreviewLang] = useState<Lang>(lang);
  const [device, setDevice] = useState<"phone" | "web">("phone");
  const [find, setFind] = useState("");
  const [confirmReset, setConfirmReset] = useState(false);
  const [showPreview, setShowPreview] = useState(() => typeof window === "undefined" || window.innerWidth > 640);

  const load = (data: Branding) => {
    const full = withDefaults(data);
    setB(full);
    setSavedJson(JSON.stringify(full));
  };
  useEffect(() => { get<Branding>(loadPath).then(load).catch((e) => setError(e.message)); }, [loadPath]);
  useEffect(() => {
    // Real content for the preview, from the public page (suspended companies have none: samples are used).
    get<PublicCompany>(`/api/public/companies/${slug}`).then(setInfo).catch(() => {});
    get<TravelPackage[]>(`/api/public/companies/${slug}/packages`).then(setPkgs).catch(() => {});
  }, [slug]);
  const dirty = !!b && JSON.stringify(b) !== savedJson;
  useEffect(() => {
    if (!dirty) return;
    const warn = (e: BeforeUnloadEvent) => { e.preventDefault(); e.returnValue = ""; };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  if (!b) return error ? <ErrorBox error={error} /> : <div className="skeleton" style={{ height: 420, borderRadius: 24 }} />;

  const agent = info?.ai_agent_name ?? "Sara";
  const companyName = name ?? info?.name ?? "";
  const update = (patch: Partial<Branding>) => { setSaved(false); setB({ ...b, ...patch }); };
  const set = <K extends keyof Branding>(k: K, v: Branding[K]) => update({ [k]: v } as Partial<Branding>);
  const setEl = (k: keyof PageElements, v: boolean) => update({ elements: { ...b.elements, [k]: v } });
  const setCards = (patch: Partial<CardDesign>) => update({ cards: { ...b.cards, ...patch } });
  const setText = (l: Lang, key: string, v: string) => {
    const own = { ...b.texts[l] };
    if (v.trim()) own[key] = v; else delete own[key];
    update({ texts: { ...b.texts, [l]: own } });
  };

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

  const save = async (e?: FormEvent) => {
    e?.preventDefault();
    setError(null);
    setSaving(true);
    try {
      const body: Partial<Branding> = { ...b };
      delete body.version;
      if (!owner) {
        delete body.dashboard_color;
        delete body.dashboard_sidebar;
      }
      load(await patch<Branding>(loadPath, body));
      setSaved(true);
      onSaved?.();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const resetAll = () => {
    setConfirmReset(false);
    update({ ...DEFAULTS, elements: { ...DEFAULT_ELEMENTS, powered_by: owner ? true : b.elements.powered_by } });
  };

  const activeTheme = THEMES.find((x) => x.p === b.primary_color.toLowerCase() && x.a === b.accent_color.toLowerCase());

  // Contrast warnings with the colours the page really uses.
  const vars = pageVars(b);
  const bg = vars["--sf-bg"] ?? STD.bg;
  const fg = vars["--sf-text"] ?? STD.text;
  const warnings: string[] = [];
  if (contrastRatio(fg, bg) < 4.5) warnings.push(t("The text colour is hard to read on the background."));
  if (contrastRatio(vars["--brand"], bg) < 3) warnings.push(t("Buttons and highlighted words don't stand out from the background."));
  if (b.surface_color && contrastRatio(fg, b.surface_color) < 4.5) warnings.push(t("The text is hard to read on the cards."));

  const tabs: { id: Tab; label: string; icon: ReactNode }[] = [
    { id: "theme", label: t("Theme & colours"), icon: <PaintBrush /> },
    { id: "texts", label: t("Texts"), icon: <TextT /> },
    { id: "layout", label: t("Sections & layout"), icon: <Layout /> },
    { id: "photos", label: t("Photos"), icon: <Images /> },
    { id: "cards", label: t("Package cards"), icon: <Cards /> },
    ...(owner ? [{ id: "dashboard" as Tab, label: t("Employee dashboard"), icon: <UserGear /> }] : []),
  ];

  const pickTextLang = (l: Lang) => { setTextLang(l); setPreviewLang(l); };
  const q = find.trim().toLowerCase();

  // What the preview shows: the real customer page with the draft design.
  const previewCompany: PublicCompany = {
    name: companyName, slug, ai_agent_name: agent, welcome_message: info?.welcome_message ?? "", currency: info?.currency ?? "OMR",
    whatsapp_number: info?.whatsapp_number ?? null, contact_email: info?.contact_email ?? null, contact_phone: info?.contact_phone ?? null,
    branding: b,
  };

  const langTabs = (
    <div className="seg pe-langs" role="tablist" aria-label={t("Language")}>
      <button type="button" role="tab" aria-selected={textLang === "en"} className={textLang === "en" ? "active" : ""} onClick={() => pickTextLang("en")}>English</button>
      <button type="button" role="tab" aria-selected={textLang === "ar"} className={textLang === "ar" ? "active" : ""} onClick={() => pickTextLang("ar")} lang="ar">العربية</button>
    </div>
  );

  const field = (f: TextField, l: Lang = textLang) => (
    <TextInput key={`${l}-${f.key}`} id={`pe-${l}-${f.key}`} label={t(f.label)} lang={l} max={f.max} long={f.long}
      value={b.texts[l][f.key] ?? ""} onChange={(v) => setText(l, f.key, v)}
      placeholder={defaultText(l, f.key, agent, companyName, !!info?.whatsapp_number)}
      hint={f.vars ? t("You can write {agent} for the consultant's name.") + (f.vars.includes("company") ? ` ${t("{company} is your company name.")}` : "") : undefined} />
  );
  const own = (key: keyof Branding, label: string, max: number, placeholder: string, long?: boolean, hint?: string) => (
    <TextInput key={`${textLang}-${String(key)}`} id={`pe-${String(key)}`} label={label} lang={textLang} max={max} long={long}
      value={String(b[key] ?? "")} onChange={(v) => set(key, v as never)} placeholder={placeholder} hint={hint} />
  );
  const L = textLang;
  const extraFields: Record<string, ReactNode[]> = {
    hero: [
      own(`hero_title_${L}` as keyof Branding, t("Full title (replaces the two parts below)"), 120, L === "ar" ? "وين وجهتك الجاية؟" : "Where to next?", false,
        t("The last word of the title is highlighted.")),
      own(`hero_text_${L}` as keyof Branding, t("Text under the title"), 400, defaultText(L, "webLead", agent, companyName, false), true,
        t("On phones it is shown only when you write your own.")),
    ],
    about: [
      own(`about_title_${L}` as keyof Branding, t("About title"), 120, L === "ar" ? "من نحن" : "About us"),
      own(`about_${L}` as keyof Branding, t("About text"), 3000, t("Tell customers who you are. Leave empty to hide the about text."), true),
    ],
  };

  return (
    <form className="bz pe" onSubmit={save}>
      <div className="bz-form">
        <div className="cd-tabs pe-tabs" role="tablist" aria-label={t("Customer page design")}>
          {tabs.map((x) => (
            <button key={x.id} type="button" role="tab" aria-selected={tab === x.id} className={tab === x.id ? "active" : ""} onClick={() => setTab(x.id)}>
              {x.icon}<span>{x.label}</span>
            </button>
          ))}
        </div>

        {tab === "theme" && (<>
          <section className="ad-card">
            <h2 className="ad-card-title"><span className="ad-card-icon"><PaintBrush /></span>{t("Colours")}</h2>
            <div className="ad-section-label">{t("Ready themes")}</div>
            <div className="bz-themes">
              {THEMES.map((p) => {
                const on = activeTheme?.name === p.name;
                return (
                  <button type="button" key={p.name} className={`bz-theme ${on ? "active" : ""}`} aria-pressed={on} onClick={() => {
                    update({ primary_color: p.p, accent_color: p.a, ...(owner ? { dashboard_color: p.p } : {}) });
                  }}>
                    <span className="bz-theme-dots"><i style={{ background: p.p }} /><i style={{ background: p.a }} /></span>
                    {t(p.name)}
                    {on && <Check weight="bold" className="bz-theme-check" />}
                  </button>
                );
              })}
            </div>
            <div className="ad-grid-2">
              <ColorInput label={t("Main colour")} value={b.primary_color} onChange={(v) => v && set("primary_color", v)}
                hint={t("Buttons, links and the highlighted word.")} />
              <ColorInput label={t("Accent colour")} value={b.accent_color} onChange={(v) => v && set("accent_color", v)}
                hint={t("The AI consultant's picture.")} />
              <ColorInput label={t("Page background")} value={b.bg_color} fallback={STD.bg} onChange={(v) => set("bg_color", v)} />
              <ColorInput label={t("Cards and fields")} value={b.surface_color} fallback="#2b2928" onChange={(v) => set("surface_color", v)} />
              <ColorInput label={t("Text colour")} value={b.text_color} fallback={STD.text} onChange={(v) => set("text_color", v)} />
              <ColorInput label={t("Highlight colour")} value={b.highlight_color} fallback="#ff5c9d" onChange={(v) => set("highlight_color", v)}
                hint={t("\"Live\", few seats left, and your team in the chat.")} />
            </div>
            {warnings.length > 0 && (
              <div className="pe-warn" role="status">
                <Warning weight="fill" />
                <div>{warnings.map((w) => <p key={w}>{w}</p>)}<p className="pe-warn-hint">{t("Customers may not be able to read the page. Try a darker background or a lighter text colour.")}</p></div>
              </div>
            )}
          </section>
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
            <p className="field-hint">{t("The banner title and text are in the Texts tab.")}</p>
          </section>
        </>)}

        {tab === "texts" && (
          <section className="ad-card">
            <h2 className="ad-card-title"><span className="ad-card-icon"><TextT /></span>{t("Texts of the page")}</h2>
            <p className="ad-card-note">{t("Every text your customers see. Empty fields use the standard text shown in grey. Write each language separately.")}</p>
            <div className="pe-texts-top">
              {langTabs}
              <label className="pe-find">
                <MagnifyingGlass aria-hidden="true" />
                <input type="search" value={find} onChange={(e) => setFind(e.target.value)} placeholder={t("Find a text")} aria-label={t("Find a text")} />
              </label>
            </div>
            {TEXT_GROUPS.map((g) => {
              const fields = g.fields.filter((f) => !q || t(f.label).toLowerCase().includes(q)
                || defaultText(L, f.key, agent, companyName, false).toLowerCase().includes(q) || (b.texts[L][f.key] ?? "").toLowerCase().includes(q));
              const extra = q ? [] : extraFields[g.id] ?? [];
              if (!fields.length && !extra.length) return null;
              const changed = g.fields.filter((f) => b.texts[L][f.key]).length;
              return (
                <details key={g.id} className="pe-group" open={!!q || g.id === "hero"}>
                  <summary>
                    <span>{t(g.title)}</span>
                    {changed > 0 && <span className="badge">{t("{n} changed", { n: changed })}</span>}
                  </summary>
                  <div className="pe-group-body">
                    {extra}
                    {fields.map((f) => field(f))}
                  </div>
                </details>
              );
            })}
          </section>
        )}

        {tab === "layout" && (<>
          <section className="ad-card">
            <h2 className="ad-card-title"><span className="ad-card-icon"><Layout /></span>{t("Page structure")}</h2>
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
            <p className="field-hint">{t("About us and Contact are shown together, where the first of the two is.")}</p>
          </section>
          <section className="ad-card">
            <h2 className="ad-card-title">{t("Show or hide smaller parts")}</h2>
            <ul className="bz-sections pe-elements">
              {ELEMENT_LABELS.map((x) => {
                const locked = x.key === "powered_by" && !owner;
                return (
                  <li key={x.key} className={b.elements[x.key] ? "" : "off"}>
                    <Switch checked={b.elements[x.key]} disabled={locked} onChange={(v) => setEl(x.key, v)} label={t(x.label)}
                      hint={locked ? t("Always shown. Only the platform can hide it.") : x.hint ? t(x.hint) : undefined} />
                  </li>
                );
              })}
            </ul>
          </section>
        </>)}

        {tab === "photos" && (
          <section className="ad-card">
            <h2 className="ad-card-title"><span className="ad-card-icon"><Images /></span>{t("Photos")}</h2>
            <div className="pe-photos">
              <div className="field">
                <span className="field-label">{t("Logo")}</span>
                <ImageUpload value={b.logo} onChange={(url) => set("logo", url)} endpoint={uploadPath} maxSide={512} contain />
                <span className="field-hint">{t("PNG or SVG, square works best.")} {t("Shown on the customer page and in the employee dashboard.")}</span>
              </div>
              <div className="field">
                <span className="field-label">{t("Top banner photo")}</span>
                <ImageUpload value={b.hero_image} endpoint={uploadPath} maxSide={1920}
                  onChange={(url) => update({ hero_image: url, hero_style: url ? "image" : b.hero_style === "image" ? "gradient" : b.hero_style })} />
                <span className="field-hint">{t("Behind the title at the top of the page.")}</span>
              </div>
              <div className="field">
                <span className="field-label">{t("About us photo")}</span>
                <ImageUpload value={b.about_image} onChange={(url) => set("about_image", url)} endpoint={uploadPath} maxSide={1600} />
                <span className="field-hint">{t("Your team or office, next to the about text.")}</span>
              </div>
              <div className="field">
                <span className="field-label">{t("About us background")}</span>
                <ImageUpload value={b.about_bg_image} onChange={(url) => set("about_bg_image", url)} endpoint={uploadPath} maxSide={1920} />
              </div>
              <div className="field">
                <span className="field-label">{t("\"How booking works\" background")}</span>
                <ImageUpload value={b.how_bg_image} onChange={(url) => set("how_bg_image", url)} endpoint={uploadPath} maxSide={1920} />
              </div>
            </div>
            <p className="field-hint">{t("Background photos are darkened so the text stays readable. Package photos are set on each package.")}</p>
          </section>
        )}

        {tab === "cards" && (
          <section className="ad-card">
            <h2 className="ad-card-title"><span className="ad-card-icon"><Cards /></span>{t("Package cards")}</h2>
            <div className="field">
              <span className="field-label">{t("Card style")}</span>
              <div className="pe-styles" role="group" aria-label={t("Card style")}>
                {([
                  { v: "poster", label: t("Poster"), hint: t("Big destination art with the name"), icon: <SquaresFour /> },
                  { v: "photo", label: t("Photo first"), hint: t("Photo on top, details and button below"), icon: <Images /> },
                  { v: "compact", label: t("Compact list"), hint: t("Small rows, many trips at a glance"), icon: <Rows /> },
                ] as const).map((o) => (
                  <button key={o.v} type="button" className={`pe-style ${b.cards.style === o.v ? "active" : ""}`} aria-pressed={b.cards.style === o.v}
                    onClick={() => setCards({ style: o.v })}>
                    <span className={`pe-style-pic pe-pic-${o.v}`} aria-hidden="true"><i /><i /><i /></span>
                    <strong>{o.icon}{o.label}</strong><small>{o.hint}</small>
                  </button>
                ))}
              </div>
            </div>
            <div className="ad-grid-2">
              <div className="field">
                <span className="field-label">{t("Card corners")}</span>
                <Seg label={t("Card corners")} value={b.card_style} onChange={(v) => set("card_style", v)} options={[
                  { v: "rounded", label: t("Rounded") }, { v: "square", label: t("Square") }]} />
              </div>
              <div className="field">
                <span className="field-label">{t("Cards per row on computers")}</span>
                <Seg label={t("Cards per row on computers")} value={b.cards.columns} onChange={(v) => setCards({ columns: v })}
                  options={[{ v: 2, label: "2" }, { v: 3, label: "3" }, { v: 4, label: "4" }]} />
              </div>
            </div>
            <div className="ad-section-label md-label">{t("Shown on each card")}</div>
            <ul className="bz-sections pe-elements">
              {([
                ["show_price", "Price"], ["per_person", "\"per person\" after the price"], ["show_duration", "Number of days"],
                ["show_hotel", "Hotel"], ["show_next_date", "Next departure date"], ["show_seats", "Seats left"],
                ["show_tags", "Tags"], ["show_button", "Book button"],
              ] as [keyof CardDesign, string][]).map(([k, label]) => (
                <li key={k} className={b.cards[k] ? "" : "off"}>
                  <Switch checked={!!b.cards[k]} disabled={k === "per_person" && !b.cards.show_price}
                    onChange={(v) => setCards({ [k]: v } as Partial<CardDesign>)} label={t(label)} />
                </li>
              ))}
            </ul>
            <div className="ad-section-label md-label">{t("Button texts")}</div>
            {langTabs}
            <div className="ad-grid-2 pe-btn-texts">
              {TEXT_GROUPS.find((g) => g.id === "buttons")!.fields.map((f) => field(f))}
            </div>
          </section>
        )}

        {tab === "dashboard" && owner && (
          <section className="ad-card">
            <h2 className="ad-card-title">{t("Employee dashboard")}</h2>
            <p className="ad-card-note">{t("Only you (the platform owner) can change these. Company employees see them after their next page load.")}</p>
            <div className="ad-grid-2">
              <ColorInput label={t("Dashboard main colour")} value={b.dashboard_color} onChange={(v) => v && set("dashboard_color", v)} />
              <ColorInput label={t("Sidebar colour")} value={b.dashboard_sidebar} onChange={(v) => v && set("dashboard_sidebar", v)} />
            </div>
            <button type="button" className="btn btn-sm btn-soft" onClick={() => set("dashboard_color", b.primary_color)}>
              {t("Use the customer page colour")}
            </button>
            <div className="ad-section-label md-label">{t("Staff dashboard preview")}</div>
            <DashboardPreview b={b} name={companyName} />
          </section>
        )}

        <div className="bz-bar pe-bar">
          <div className="bz-bar-msg" aria-live="polite">
            <ErrorBox error={error} />
            {saved && !dirty && <div className="ok-box ad-notice">{t("Saved. Customers see the new design right away.")}</div>}
            {dirty && <span className="pe-unsaved"><span className="pe-dot" />{t("Unsaved changes")}</span>}
          </div>
          <button type="button" className="btn btn-ghost" onClick={() => setConfirmReset(true)}><ArrowCounterClockwise />{t("Reset all to default")}</button>
          <a className="btn btn-ghost" href={`/c/${slug}`} target="_blank" rel="noreferrer"><ArrowSquareOut />{t("Open customer page")}</a>
          <button className="btn btn-primary" disabled={saving || !dirty} aria-busy={saving}>{saving ? t("Saving…") : t("Save design")}</button>
        </div>
        {confirmReset && (
          <div className="pe-confirm" role="alertdialog" aria-labelledby="pe-reset-q">
            <p id="pe-reset-q"><strong>{t("Reset the whole page to the standard design?")}</strong> {t("Colours, texts, sections, photos and package cards go back to the standard. Your logo stays. Nothing changes for customers until you save.")}</p>
            <div className="pe-confirm-actions">
              <button type="button" className="btn" onClick={() => setConfirmReset(false)}><X />{t("Cancel")}</button>
              <button type="button" className="btn btn-danger" onClick={resetAll}><ArrowCounterClockwise />{t("Reset all to default")}</button>
            </div>
          </div>
        )}
      </div>

      <aside className="bz-preview pe-preview" aria-label={t("Live preview")}>
        <div className="pe-preview-head">
          <div className="bz-preview-label"><span className="live-dot" aria-hidden="true" />{t("Live preview")}</div>
          <div className="seg" role="group" aria-label={t("Device")}>
            <button type="button" className={device === "phone" ? "active" : ""} aria-pressed={device === "phone"} onClick={() => setDevice("phone")} title={t("Phone")}><DeviceMobile /><span className="sr-only">{t("Phone")}</span></button>
            <button type="button" className={device === "web" ? "active" : ""} aria-pressed={device === "web"} onClick={() => setDevice("web")} title={t("Computer")}><Monitor /><span className="sr-only">{t("Computer")}</span></button>
          </div>
          <div className="seg" role="group" aria-label={t("Language")}>
            <button type="button" className={previewLang === "en" ? "active" : ""} aria-pressed={previewLang === "en"} onClick={() => setPreviewLang("en")}>EN</button>
            <button type="button" className={previewLang === "ar" ? "active" : ""} aria-pressed={previewLang === "ar"} onClick={() => setPreviewLang("ar")} lang="ar">ع</button>
          </div>
          <button type="button" className="btn btn-sm btn-ghost" aria-expanded={showPreview} onClick={() => setShowPreview((v) => !v)}>
            {showPreview ? t("Hide preview") : t("Show preview")}
          </button>
        </div>
        {showPreview && <PreviewFrame key={device} width={device === "phone" ? 390 : 1280} height={device === "phone" ? 780 : 820}>
          <StorefrontPage slug={slug} company={previewCompany} packages={pkgs.length ? pkgs : SAMPLE} lang={previewLang}
            setLang={setPreviewLang} layout={device} preview />
        </PreviewFrame>}
        <p className="field-hint pe-preview-note">{t("You can click around in the preview. The chat does not send messages here.")}</p>
      </aside>
    </form>
  );
}

/** Fills fields missing from an older saved design (or an older server) with the standard values. */
function withDefaults(data: Branding): Branding {
  return {
    ...DEFAULTS, ...data,
    elements: { ...DEFAULT_ELEMENTS, ...data.elements },
    cards: { ...DEFAULT_CARDS, ...data.cards },
    texts: { en: { ...data.texts?.en }, ar: { ...data.texts?.ar } },
  } as Branding;
}

/** The real page at its real size (390 px phone or 1280 px computer), scaled down to fit the column.
 *  The transform makes it the frame for the page's fixed parts (chat button, package window). */
function PreviewFrame({ width, height, children }: { width: number; height: number; children: ReactNode }) {
  const box = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(0.8);
  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const fit = () => setScale(Math.min(1, el.clientWidth / width));
    fit();
    const ro = new ResizeObserver(fit);
    ro.observe(el);
    return () => ro.disconnect();
  }, [width]);
  // Links (WhatsApp, phone, e-mail, "Powered by") don't leave the editor.
  const stopLinks = (e: MouseEvent) => {
    if ((e.target as HTMLElement).closest("a")) e.preventDefault();
  };
  const style = useMemo(() => ({ width, height, transform: `scale(${scale})` }) as CSSProperties, [width, height, scale]);
  return (
    <div ref={box} className="pe-frame" style={{ height: height * scale }} onClickCapture={stopLinks}>
      <div className="pe-frame-page" style={style}>
        <div className="pe-frame-scroll">{children}</div>
      </div>
    </div>
  );
}

/** Staff dashboard in miniature, in the dark shell style with the chosen sidebar and main colour. */
function DashboardPreview({ b, name }: { b: Branding; name: string }) {
  return (
    <div className="dash-mini" style={dashboardVars(b.dashboard_color, b.dashboard_sidebar) as CSSProperties} aria-hidden="true">
      <div className="dash-mini-side">
        <div className="dash-mini-brand">
          {b.logo ? <img src={b.logo} alt="" /> : <GhanjahMark dark={isDark(b.dashboard_sidebar)} />}
          <span>{name}</span>
        </div>
        <i className="on" /><i /><i /><i /><i />
        <span className="dash-mini-user" />
      </div>
      <div className="dash-mini-main">
        <span className="dash-mini-hello" />
        <div className="dash-mini-kpis"><i className="hero" /><i /><i /><i /></div>
        <div className="dash-mini-chart">{[40, 65, 50, 80, 60, 90, 75, 55, 85, 70].map((h, i) => (
          <i key={i} style={{ height: `${h}%` }}><b style={{ height: `${30 + (i % 3) * 10}%` }} /></i>
        ))}</div>
        <span className="dash-mini-btn" />
      </div>
    </div>
  );
}
