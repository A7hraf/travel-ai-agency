import { useState } from "react";
import { useI18n } from "../lang";
import type { StoryItem, StoryKey, StorySection } from "../types";
import type { Lang } from "./Money";
import ImageUpload from "./ImageUpload";
import { ArrowDown, ArrowUp, Plus, Trash } from "./Icon";
import { STORY_KEYS } from "./storefront/Stories";

export const MAX_STORY_ITEMS = 12;

export const STORY_LABELS: Record<StoryKey, string> = {
  brand: "The Brand",
  experiences: "Experiences",
  services: "Services",
  leadership: "Leadership",
  community: "The Community",
};

/** What each section is for, and what a card holds there. */
const STORY_HELP: Record<StoryKey, { note: string; card: string; tag?: string; subtitle?: string }> = {
  brand: { note: "Who you are: one card each for your mission, philosophy and brand strategy.", card: "Pillar" },
  experiences: { note: "The experiences you offer. Group them with a tag, for example \"Inside Oman\" and \"Around the world\": customers can filter by tag.",
    card: "Experience", tag: "Group (tag)", subtitle: "Short line (duration, season…)" },
  services: { note: "Everything you arrange for the traveller: flights, transport, stays, visas, insurance…", card: "Service", subtitle: "Short line" },
  leadership: { note: "How the idea was built, and the people behind it.", card: "Person", subtitle: "Role" },
  community: { note: "Your members' community and what members get. A \"Ask to join\" button opens the chat.",
    card: "Member level or benefit", tag: "Label (for example \"By invitation\")", subtitle: "Short line" },
};

const EMPTY_ITEM: StoryItem = { tag_en: "", tag_ar: "", title_en: "", title_ar: "", subtitle_en: "", subtitle_ar: "", text_en: "", text_ar: "", image: null };
export const EMPTY_STORY: StorySection = { kicker_en: "", kicker_ar: "", title_en: "", title_ar: "", intro_en: "", intro_ar: "", image: null, items: [] };

function Input({ id, label, value, onChange, max, long, lang, placeholder }: {
  id: string; label: string; value: string; onChange: (v: string) => void; max: number; long?: boolean; lang: Lang; placeholder?: string;
}) {
  const dir = lang === "ar" ? "rtl" : "ltr";
  return (
    <div className="field">
      <label className="field-label" htmlFor={id}>{label}</label>
      {long
        ? <textarea id={id} rows={4} value={value} maxLength={max} dir={dir} lang={lang} placeholder={placeholder} onChange={(e) => onChange(e.target.value)} />
        : <input id={id} value={value} maxLength={max} dir={dir} lang={lang} placeholder={placeholder} onChange={(e) => onChange(e.target.value)} />}
    </div>
  );
}

/** Editor of the story sections (The Brand, Experiences, Services, Leadership, The Community). */
export default function StoryEditor({ stories, onChange, uploadPath, lang, langTabs, isOn, turnOn }: {
  stories: Partial<Record<StoryKey, StorySection>>;
  onChange: (key: StoryKey, section: StorySection) => void;
  uploadPath: string;
  lang: Lang;
  langTabs: React.ReactNode;
  isOn: (key: StoryKey) => boolean;
  turnOn: (key: StoryKey) => void;
}) {
  const { t } = useI18n();
  const [key, setKey] = useState<StoryKey>("brand");
  const s = { ...EMPTY_STORY, ...stories[key] };
  const help = STORY_HELP[key];
  const L = lang;
  const set = (patch: Partial<StorySection>) => onChange(key, { ...s, ...patch });
  const setItem = (i: number, patch: Partial<StoryItem>) => set({ items: s.items.map((it, j) => (j === i ? { ...it, ...patch } : it)) });
  const move = (i: number, step: number) => {
    const items = [...s.items];
    [items[i], items[i + step]] = [items[i + step], items[i]];
    set({ items });
  };
  const sk = (f: string) => `${f}_${L}` as keyof StorySection;
  const ik = (f: string) => `${f}_${L}` as keyof StoryItem;

  return (
    <>
      <section className="gx-card">
        <h2 className="gx-card-title">{t("Brand sections")}</h2>
        <p className="gx-card-note">{t("Extra sections that tell your story. Each one is shown only when it has content and is switched on in Sections & layout.")}</p>
        <div className="seg gx-story-keys" role="tablist" aria-label={t("Brand sections")}>
          {STORY_KEYS.map((k) => (
            <button key={k} type="button" role="tab" aria-selected={key === k} className={key === k ? "active" : ""} onClick={() => setKey(k)}>
              {t(STORY_LABELS[k])}
            </button>
          ))}
        </div>
        {!isOn(key) && (
          <div className="gx-notice gx-story-off">
            <span>{t("This section is switched off, so customers don't see it.")}</span>
            <button type="button" className="btn btn-sm btn-soft" onClick={() => turnOn(key)}>{t("Show it on the page")}</button>
          </div>
        )}
      </section>

      <section className="gx-card">
        <div className="gx-story-head">
          <h2 className="gx-card-title">{t(STORY_LABELS[key])}</h2>
          {langTabs}
        </div>
        <p className="gx-card-note">{t(help.note)}</p>
        <Input id={`st-kicker-${L}`} label={t("Small line above the title (also the menu link)")} lang={L} max={80}
          value={String(s[sk("kicker")])} onChange={(v) => set({ [sk("kicker")]: v })} placeholder={t(STORY_LABELS[key])} />
        <Input id={`st-title-${L}`} label={t("Title")} lang={L} max={120} value={String(s[sk("title")])} onChange={(v) => set({ [sk("title")]: v })} />
        <Input id={`st-intro-${L}`} label={t("Intro text")} lang={L} max={1500} long value={String(s[sk("intro")])} onChange={(v) => set({ [sk("intro")]: v })} />
        <div className="field">
          <span className="field-label">{t("Section photo (optional)")}</span>
          <ImageUpload value={s.image} onChange={(url) => set({ image: url })} endpoint={uploadPath} maxSide={1920} />
        </div>
      </section>

      <section className="gx-card">
        <h2 className="gx-card-title">{t("Cards")} <span className="gx-muted">{s.items.length} / {MAX_STORY_ITEMS}</span></h2>
        {s.items.length === 0 && <p className="gx-card-note">{t("No cards yet.")}</p>}
        <ol className="gx-story-items">
          {s.items.map((it, i) => (
            <li key={i} className="gx-story-item">
              <div className="gx-story-item-head">
                <strong>{t(help.card)} {i + 1}</strong>
                <span className="spacer" />
                <button type="button" className="icon-btn" disabled={i === 0} onClick={() => move(i, -1)} aria-label={`${t("Move up")}: ${i + 1}`}><ArrowUp /></button>
                <button type="button" className="icon-btn" disabled={i === s.items.length - 1} onClick={() => move(i, 1)} aria-label={`${t("Move down")}: ${i + 1}`}><ArrowDown /></button>
                <button type="button" className="icon-btn" onClick={() => set({ items: s.items.filter((_, j) => j !== i) })} aria-label={`${t("Remove")}: ${i + 1}`}><Trash /></button>
              </div>
              {help.tag && <Input id={`st-${i}-tag-${L}`} label={t(help.tag)} lang={L} max={40} value={String(it[ik("tag")])} onChange={(v) => setItem(i, { [ik("tag")]: v })} />}
              <Input id={`st-${i}-title-${L}`} label={t(key === "leadership" ? "Name" : "Title")} lang={L} max={120} value={String(it[ik("title")])} onChange={(v) => setItem(i, { [ik("title")]: v })} />
              {help.subtitle && <Input id={`st-${i}-sub-${L}`} label={t(help.subtitle)} lang={L} max={120} value={String(it[ik("subtitle")])} onChange={(v) => setItem(i, { [ik("subtitle")]: v })} />}
              <Input id={`st-${i}-text-${L}`} label={t("Text")} lang={L} max={1500} long value={String(it[ik("text")])} onChange={(v) => setItem(i, { [ik("text")]: v })} />
              <div className="field">
                <span className="field-label">{t("Photo (optional)")}</span>
                <ImageUpload value={it.image} onChange={(url) => setItem(i, { image: url })} endpoint={uploadPath} maxSide={1280} />
              </div>
            </li>
          ))}
        </ol>
        <button type="button" className="btn btn-soft" disabled={s.items.length >= MAX_STORY_ITEMS}
          onClick={() => set({ items: [...s.items, { ...EMPTY_ITEM }] })}><Plus />{t("Add a card")}</button>
      </section>
    </>
  );
}
