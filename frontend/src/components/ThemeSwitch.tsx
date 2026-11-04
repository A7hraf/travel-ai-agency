/** Light / Dark / Auto switch (see themeMode.ts). Two looks:
 *  - "icon": one compact button that cycles Light → Dark → Auto (sidebar footer, login top bar);
 *  - "segmented": three labelled buttons (My account, the phone menu). */
import type { ComponentType } from "react";
import { useI18n } from "../lang";
import { THEME_MODES, ThemeMode, useTheme } from "../themeMode";
import { IconProps, Monitor, Moon, Sun } from "./Icon";

const ICONS: Record<ThemeMode, ComponentType<IconProps>> = { light: Sun, dark: Moon, auto: Monitor };
const LABELS: Record<ThemeMode, string> = { light: "Light", dark: "Dark", auto: "Auto" };

export function ThemeSwitch({ variant = "icon", className = "" }: { variant?: "icon" | "segmented"; className?: string }) {
  const { t } = useI18n();
  const { mode, theme, setMode } = useTheme();

  if (variant === "segmented") {
    return (
      <div className={`seg theme-seg ${className}`} role="radiogroup" aria-label={t("Appearance")}>
        {THEME_MODES.map((m) => {
          const Icon = ICONS[m];
          return (
            <button key={m} type="button" role="radio" aria-checked={mode === m} className={mode === m ? "active" : ""}
              onClick={() => setMode(m)} title={m === "auto" ? t("Follow the device setting") : undefined}>
              <Icon size={17} weight={mode === m ? "fill" : "duotone"} aria-hidden="true" />
              {t(LABELS[m])}
            </button>
          );
        })}
      </div>
    );
  }

  const next = THEME_MODES[(THEME_MODES.indexOf(mode) + 1) % THEME_MODES.length];
  const Icon = ICONS[mode];
  const now = mode === "auto"
    ? t("Appearance: Auto (now {theme})", { theme: t(LABELS[theme]) })
    : t("Appearance: {mode}", { mode: t(LABELS[mode]) });
  const label = `${now}. ${t("Switch to {mode}", { mode: t(LABELS[next]) })}`;
  return (
    <button type="button" className={`theme-switch ${className}`} onClick={() => setMode(next)} aria-label={label} title={label}>
      <Icon size={16} weight="duotone" aria-hidden="true" />
    </button>
  );
}
