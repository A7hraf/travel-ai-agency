import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { get } from "../api";
import { PageTitle } from "../components/admin/AdminUI";
import { Star } from "../components/Icon";
import { Empty, ErrorBox, Loading } from "../components/ui";
import { useI18n } from "../lang";
import { dateTime } from "../util";

interface FeedbackRow { id: number; customer_id: number; customer_name: string | null; ticket_id: number; reference: string; title: string; rating: number; comment: string | null; source: string; created_at: string }
interface FeedbackList { average: number | null; count: number; by_rating: Record<string, number>; feedback: FeedbackRow[] }

/** What customers said after their trips (from their trips page or the chat). */
export default function Feedback() {
  const { t } = useI18n();
  const [data, setData] = useState<FeedbackList | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = () => get<FeedbackList>("/api/feedback").then((d) => { setData(d); setError(null); }).catch((e) => setError((e as Error).message));
  useEffect(() => { load(); }, []);
  const head = <PageTitle kicker={t("Agency workspace")} title={t("Trip feedback")}
    subtitle={t("Ratings customers gave after their trips. The AI asks on WhatsApp when a trip ends, and customers can rate on their trips page.")} />;
  if (!data) return <div>{head}{error ? <ErrorBox error={error} onRetry={load} /> : <Loading height={240} />}</div>;
  const max = Math.max(1, ...Object.values(data.by_rating));
  return (
    <div>
      {head}
      <div className="gx-b2b-meters">
        <div className="gx-b2b-meter">
          <div className="gx-b2b-num tnum">{data.average ?? "—"}<span className="muted"> / 5</span></div>
          <div className="muted small">{t("{n} ratings", { n: data.count })}</div>
        </div>
        <div className="gx-b2b-meter gx-fb-bars">
          {[5, 4, 3, 2, 1].map((r) => (
            <div key={r} className="gx-fb-bar"><span>{r} <Star weight="fill" /></span>
              <div className="tm-meter"><div style={{ width: `${(data.by_rating[r] / max) * 100}%` }} /></div><span className="tnum">{data.by_rating[r]}</span></div>
          ))}
        </div>
      </div>
      {data.feedback.length === 0 ? <Empty>{t("No feedback yet.")}</Empty> : (
        <ul className="gx-req-list">
          {data.feedback.map((f) => (
            <li key={f.id} className="gx-card gx-fb">
              <div className="gx-row-between">
                <span className="gx-fb-stars" aria-label={`${f.rating} / 5`}>{[1, 2, 3, 4, 5].map((n) => <Star key={n} weight="fill" className={n <= f.rating ? "on" : ""} />)}</span>
                <span className="muted small">{dateTime(f.created_at)} · {f.source === "chat" ? t("in the chat") : t("on the trips page")}</span>
              </div>
              {f.comment && <p dir="auto">“{f.comment}”</p>}
              <div className="muted small"><Link to={`/app/customers/${f.customer_id}`} dir="auto">{f.customer_name ?? `#${f.customer_id}`}</Link> · {f.reference} · <span dir="auto">{f.title}</span></div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
