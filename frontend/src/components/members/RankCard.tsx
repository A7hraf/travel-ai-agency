import { useState } from "react";
import { put } from "../../api";
import { useAuth } from "../../auth";
import { useI18n } from "../../lang";
import { MEMBER_LEVELS, type MemberLevel } from "../../types";
import { Crown } from "../Icon";
import { ErrorBox } from "../ui";
import MemberBadge, { useLevelName } from "./MemberBadge";

/** Customer page: the member rank, which only staff with members.manage can give or take away. */
export default function RankCard({ customerId, level, onChanged }: { customerId: number; level: MemberLevel | null | undefined; onChanged: () => void }) {
  const { user, can } = useAuth();
  const { t } = useI18n();
  const name = useLevelName();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (!user?.company?.member_levels) return null;
  const canSet = can("members.manage");
  const change = async (value: string) => {
    setBusy(true);
    setError(null);
    try { await put(`/api/members/${customerId}`, { level: value || null }); onChanged(); }
    catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  };
  return (
    <section className="gx-card">
      <h2 className="gx-card-title"><span className="gx-card-icon"><Crown /></span>{t("Membership")}</h2>
      <div className="gx-inline">
        {level ? <MemberBadge level={level} /> : <span className="muted">{t("Not a member")}</span>}
        {canSet && (
          <select value={level ?? ""} disabled={busy} onChange={(e) => change(e.target.value)} aria-label={t("Member rank")}>
            <option value="">{t("Not a member")}</option>
            {MEMBER_LEVELS.map((l) => <option key={l} value={l}>{name(l)?.name ?? l}</option>)}
          </select>
        )}
      </div>
      <p className="gx-card-note">{canSet ? t("Only your team gives ranks. A customer saying they are VIP in a chat changes nothing.") : t("Only colleagues with the members permission can change the rank.")}</p>
      <ErrorBox error={error} />
    </section>
  );
}
