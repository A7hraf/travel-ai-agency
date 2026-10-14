import fullDark from "../assets/brand/mark-full-reverse.svg";
import full from "../assets/brand/mark-full.svg";
import iconDark from "../assets/brand/mark-icon-reverse.svg";
import icon from "../assets/brand/mark-icon.svg";
import { useI18n } from "../lang";

/** Ghanjah (غنجة): the platform's name, in the language of the page. */
export const PLATFORM_NAME = "Ghanjah";
export const PLATFORM_NAME_AR = "غنجة";

export function usePlatformName(): string {
  const { lang } = useI18n();
  return lang === "ar" ? PLATFORM_NAME_AR : PLATFORM_NAME;
}

/** The Muscat exit stamp with the breakout plane. `dark` = drawn for a dark background. */
export function GhanjahMark({ variant = "icon", dark = false, className = "", size }: {
  variant?: "icon" | "full";
  dark?: boolean;
  className?: string;
  size?: number;
}) {
  const src = variant === "full" ? (dark ? fullDark : full) : dark ? iconDark : icon;
  return (
    <img className={`ghanjah-mark ${variant} ${className}`} src={src} alt="Ghanjah" draggable={false}
      style={size ? { width: size, height: "auto" } : undefined} />
  );
}

/** Full logo: mark, name, "AI travel from Oman" and the Arabic line. */
export function GhanjahLockup({ dark = false, compact = false }: { dark?: boolean; compact?: boolean }) {
  return (
    <div className={`ghanjah-lockup ${dark ? "dark" : ""} ${compact ? "compact" : ""}`} dir="ltr">
      <GhanjahMark variant="full" dark={dark} />
      <div className="ghanjah-words">
        <div className="ghanjah-name">Ghanjah</div>
        <div className="ghanjah-tagline">AI TRAVEL FROM OMAN</div>
        <div className="ghanjah-arabic" lang="ar" dir="rtl">غنجة · سفر ذكي من عُمان</div>
      </div>
    </div>
  );
}
