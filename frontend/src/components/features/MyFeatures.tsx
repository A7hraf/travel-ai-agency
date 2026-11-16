import { useEffect, useState } from "react";
import { get, put } from "../../api";
import { useAuth } from "../../auth";
import { useI18n } from "../../lang";
import type { User } from "../../types";
import { Sparkle } from "../Icon";
import { ErrorBox } from "../ui";
import { FeatureState, LEVEL_LABELS } from "./types";

/** The company's features and AI capabilities: what it has, how much it used, and (for its admin) which
 *  employees use the features that count employees. */
export default function MyFeatures() {
  const { t } = useI18n();
  const { user, refresh } = useAuth();
  const admin = user?.role === "company_admin";
  const [data, setData] = useState<FeatureState | null>(null);
  const [team, setTeam] = useState<User[]>([]);
  const [error, setError] = useState<string | null>(null);
  const load = () => get<FeatureState>("/api/features").then(setData).catch((e) => setError((e as Error).message));
  useEffect(() => {
    load();
    if (admin) get<User[]>("/api/users").then(setTeam).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  if (!data) return error ? <ErrorBox error={error} /> : null;
  const keys = data.catalog.filter((f) => data.grants[f.key]?.on);
  const toggle = async (person: User, key: string, on: boolean) => {
    setError(null);
    const current = (person.ai_features ?? []).filter((k) => k !== key);
    try {
      await put(`/api/team/${person.id}/features`, { features: on ? [...current, key] : current });
      setTeam(await get<User[]>("/api/users"));
      load();
      if (person.id === user?.id) refresh();
    } catch (e) { setError((e as Error).message); }
  };
  return (
    <section className="gx-card">
      <h2 className="gx-card-title">{t("Features and AI")}</h2>
      {keys.length === 0 ? <p className="muted">{t("No extra features yet. Ask the platform owner to open the ones you need.")}</p> : (
        <ul className="gx-myfeat">
          {keys.map((f) => {
            const g = data.grants[f.key];
            const used = data.usage[f.key];
            const seated = admin && g.seats != null;
            return (
              <li key={f.key} className={f.kind === "part" ? "part" : ""}>
                <div className="gx-row-between">
                  <span>{f.kind === "ai" && <Sparkle weight="fill" className="gx-feat-ai" />} {t(f.label)}</span>
                  <span className="muted small">
                    {f.metered && (g.limit ? t("{used} of {limit} {period}", { used: used ?? 0, limit: g.limit, period: t(g.period === "month" ? "this month" : "in total") })
                      : t("{used} uses", { used: used ?? 0 }))}
                  </span>
                </div>
                {g.levels.length > 0 && <div className="muted small">{g.levels.map((l) => t(LEVEL_LABELS[l] ?? l)).join(" · ")}</div>}
                {f.metered && g.limit != null && <div className="gx-meter"><span style={{ width: `${Math.min(100, ((used ?? 0) / g.limit) * 100)}%` }} /></div>}
                {seated && (
                  <div className="gx-seats">
                    <span className="muted small">{t("Who uses it ({n} of {max})", { n: data.seats?.[f.key]?.length ?? 0, max: g.seats! })}</span>
                    {team.filter((u) => u.is_active).map((u) => (
                      <label key={u.id} className="gx-feat-check">
                        <input type="checkbox" checked={(u.ai_features ?? []).includes(f.key)} onChange={(e) => toggle(u, f.key, e.target.checked)} />
                        {u.full_name}
                      </label>
                    ))}
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
      <ErrorBox error={error} />
    </section>
  );
}
