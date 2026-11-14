import { useState } from "react";
import type { StoryItem, StoryKey, StorySection } from "../../types";
import type { Lang } from "../Money";
import { ChatCircleDots } from "../Icon";
import type { StoreCtx } from "./context";

export const STORY_KEYS: StoryKey[] = ["brand", "experiences", "services", "leadership", "community"];

const pick = (lang: Lang, en: string, ar: string) => (lang === "ar" ? ar || en : en || ar).trim();

/** A story section with something to show (title, intro or at least one card). */
export function storyHasContent(s: StorySection | undefined): s is StorySection {
  return !!s && !!(s.title_en || s.title_ar || s.intro_en || s.intro_ar || s.items.length);
}

/** Label of a story section in the top menu: its kicker, or the standard name. */
export function storyNavLabel(ctx: StoreCtx, key: StoryKey): string {
  const s = ctx.company.branding.stories?.[key];
  return (s && pick(ctx.lang, s.kicker_en, s.kicker_ar)) || ctx.t.storyNav[key];
}

function Card({ ctx, k, item, i }: { ctx: StoreCtx; k: StoryKey; item: StoryItem; i: number }) {
  const { lang, t, agent } = ctx;
  const title = pick(lang, item.title_en, item.title_ar);
  const subtitle = pick(lang, item.subtitle_en, item.subtitle_ar);
  const text = pick(lang, item.text_en, item.text_ar);
  const tag = pick(lang, item.tag_en, item.tag_ar);
  const ask = k === "experiences" || k === "services";
  return (
    <article className={`sf-story-card ${item.image ? "sf-has-photo" : ""}`}>
      {item.image && <img className="sf-story-photo" src={item.image} alt="" loading="lazy" />}
      <div className="sf-story-body">
        {k === "brand" && <div className="sf-story-num" aria-hidden="true">{String(i + 1).padStart(2, "0")}</div>}
        {tag && k !== "brand" && <div className="sf-story-tag" dir="auto">{tag}</div>}
        {title && <h3 dir="auto">{title}</h3>}
        {subtitle && <div className="sf-story-sub" dir="auto">{subtitle}</div>}
        {text && <p dir="auto">{text}</p>}
        {ask && title && (
          <button type="button" className="link-btn sf-story-ask" onClick={() => ctx.ask(t.storyAskMsg(title))}>
            <ChatCircleDots />{t.storyAsk(agent)}
          </button>
        )}
      </div>
    </article>
  );
}

/** The Brand, Experiences, Services, Leadership or The Community. */
/** The members community levels, when the company has them on its page. */
function MemberLevels({ ctx }: { ctx: StoreCtx }) {
  const levels = ctx.company.members ?? [];
  return (
    <div className="sf-story-grid">
      {levels.map((lv) => {
        const perks = ctx.lang === "ar" ? lv.perks_ar : lv.perks_en;
        return (
          <article key={lv.key} className={`sf-story-card sf-level-${lv.key}`}>
            <div className="sf-story-body">
              <h3 dir="auto">{ctx.lang === "ar" ? lv.name_ar : lv.name_en}</h3>
              {perks.length > 0 && <ul className="sf-perks" dir="auto">{perks.map((p, i) => <li key={i}>{p}</li>)}</ul>}
            </div>
          </article>
        );
      })}
    </div>
  );
}

export function StoryBlock({ ctx, k }: { ctx: StoreCtx; k: StoryKey }) {
  const levels = k === "community" && (ctx.company.members?.length ?? 0) > 0;
  const stored = ctx.company.branding.stories?.[k];
  // The Community with real member levels shows even without cards of its own.
  const s: StorySection | undefined = levels && !storyHasContent(stored)
    ? { kicker_en: "", kicker_ar: "", title_en: "", title_ar: "", intro_en: "", intro_ar: "", image: null, items: [], ...(stored ?? {}) }
    : stored;
  const { lang, t } = ctx;
  const tags = storyHasContent(s)
    ? [...new Set(s.items.map((it) => pick(lang, it.tag_en, it.tag_ar)).filter(Boolean))]
    : [];
  const [tag, setTag] = useState<string | null>(null);
  if (!levels && !storyHasContent(s)) return null;
  if (!s) return null;
  const kicker = storyNavLabel(ctx, k);
  const title = pick(lang, s.title_en, s.title_ar);
  const intro = pick(lang, s.intro_en, s.intro_ar);
  const filters = k === "experiences" && tags.length > 1;
  const active = filters && tag && tags.includes(tag) ? tag : null;
  const items = active ? s.items.filter((it) => pick(lang, it.tag_en, it.tag_ar) === active) : s.items;
  return (
    <section id={k} className={`sf-story sf-story-${k}`} {...(title ? { "aria-labelledby": `sf-${k}-title` } : { "aria-label": kicker })}>
      <div className="sf-story-head">
        <div className="sf-kicker-cyan" dir="auto">{kicker}</div>
        {title && <h2 id={`sf-${k}-title`} className="sf-story-title" dir="auto">{title}</h2>}
        {s.image && <img className="sf-story-cover" src={s.image} alt="" loading="lazy" />}
        {intro && <p className="sf-story-intro" dir="auto">{intro}</p>}
      </div>
      {filters && (
        <div className="sf-chips" role="group" aria-label={kicker}>
          {[null, ...tags].map((x) => (
            <button key={x ?? "all"} type="button" className={`sf-chip ${active === x ? "sf-active" : ""}`} aria-pressed={active === x}
              onClick={() => setTag(x)} dir="auto">{x ?? t.storyAll}</button>
          ))}
        </div>
      )}
      {levels ? <MemberLevels ctx={ctx} /> : items.length > 0 && (
        <div className="sf-story-grid">
          {items.map((item, i) => <Card key={`${active ?? ""}-${i}`} ctx={ctx} k={k} item={item} i={i} />)}
        </div>
      )}
      {k === "community" && (
        <button type="button" className="sf-cta sf-story-join" onClick={() => ctx.ask(t.joinMsg)}>
          {t.joinCommunity}
        </button>
      )}
    </section>
  );
}
