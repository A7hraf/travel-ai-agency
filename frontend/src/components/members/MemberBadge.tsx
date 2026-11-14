import { useAuth } from "../../auth";
import { useI18n } from "../../lang";
import type { MemberLevel } from "../../types";
import { Crown } from "../Icon";

/** The level name of a member (in the staff's language), with a crown for priority levels. */
export function useLevelName() {
  const { user } = useAuth();
  const { lang } = useI18n();
  const levels = user?.company?.member_levels;
  return (level: MemberLevel | null | undefined) => {
    if (!level || !levels?.[level]) return null;
    const l = levels[level];
    return { name: lang === "ar" ? l.name_ar : l.name_en, priority: l.priority };
  };
}

export default function MemberBadge({ level }: { level: MemberLevel | null | undefined }) {
  const name = useLevelName()(level);
  if (!name) return null;
  return <span className={`gx-member ${name.priority ? "priority" : ""} lv-${level}`}><Crown weight="fill" />{name.name}</span>;
}
