import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { get } from "../api";
import { PageTitle } from "../components/admin/AdminUI";
import { CaretDown, Megaphone, UsersThree } from "../components/Icon";
import { ErrorBox, Loading } from "../components/ui";
import { useI18n } from "../lang";

interface Client { id: number; name: string; trips: number; spent: number; currency: string; favourite: string | null; last_contact: string | null; why: string; reachable: boolean; why_ar: string }
interface Segment { key: string; label_en: string; label_ar: string; action_en: string; action_ar: string; count: number; clients: Client[] }
interface Data { segments: Segment[]; clients: number; levels: string[]; can_target: boolean }

/** The company's clients in groups, learnt from their requests and trips, with what to do for each group. */
export default function Segments() {
  const { t, lang } = useI18n();
  const [data, setData] = useState<Data | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = () => get<Data>("/api/segments").then((d) => { setData(d); setError(null); }).catch((e) => setError((e as Error).message));
  useEffect(() => { load(); }, []);
  const money = (v: number, cur: string) => new Intl.NumberFormat(lang === "ar" ? "ar-OM" : "en-GB", { style: "currency", currency: cur, maximumFractionDigits: 0 }).format(v);
  return (
    <div className="narrow gx-narrow">
      <PageTitle kicker={t("Clients")} title={t("Client segments")}
        subtitle={t("Your clients in groups, learnt from their requests and trips, with what to do for each group. Only your company's clients.")} />
      <ErrorBox error={error} onRetry={load} />
      {!data ? (!error && <Loading height={260} />) : (
        <div className="gx-seg-list">
          {data.segments.map((s) => (
            <section key={s.key} className={`gx-card gx-seg-card ${s.count ? "" : "empty"}`}>
              <button type="button" className="gx-seg-head" aria-expanded={open === s.key} disabled={!s.count} onClick={() => setOpen(open === s.key ? null : s.key)}>
                <span className="gx-seg-count tnum">{s.count}</span>
                <span className="gx-seg-text">
                  <strong>{lang === "ar" ? s.label_ar : s.label_en}</strong>
                  <span className="muted small">{lang === "ar" ? s.action_ar : s.action_en}</span>
                </span>
                {s.count > 0 && <CaretDown className={open === s.key ? "gx-rot" : ""} />}
              </button>
              {open === s.key && (
                <>
                  <div className="gx-seg-table">
                    <table className="table">
                      <thead><tr><th>{t("Client")}</th><th>{t("Trips")}</th><th>{t("Spent")}</th><th>{t("Favourite place")}</th><th>{t("Why")}</th></tr></thead>
                      <tbody>
                        {s.clients.map((c) => (
                          <tr key={c.id}>
                            <td><Link to={`/app/customers/${c.id}`}><bdi>{c.name}</bdi></Link>{!c.reachable && <span className="muted small"> · {t("no WhatsApp")}</span>}</td>
                            <td className="tnum">{c.trips}</td>
                            <td className="tnum">{c.spent ? money(c.spent, c.currency) : "—"}</td>
                            <td><bdi>{c.favourite ?? "—"}</bdi></td>
                            <td className="muted small"><bdi>{lang === "ar" ? c.why_ar : c.why}</bdi></td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  {data.can_target && (
                    <div className="gx-form-actions">
                      <Link className="btn btn-primary btn-sm" to={`/app/broadcasts?segment=${s.key}`}><Megaphone />{t("Message this group")}</Link>
                    </div>
                  )}
                </>
              )}
            </section>
          ))}
          <p className="muted small"><UsersThree /> {t("{n} clients in all. Groups update by themselves as requests and trips change.", { n: data.clients })}</p>
        </div>
      )}
    </div>
  );
}
