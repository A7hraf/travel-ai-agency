import { useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { get } from "../api";
import { ArrowLeft, Printer } from "../components/Icon";
import QuotationSheet, { QuotationData } from "../components/QuotationSheet";
import { ErrorBox, Loading } from "../components/ui";
import { LangSwitch, useI18n } from "../lang";

/** A request's quotation for staff (draft: the choices; final: the client's choices and total), printable to PDF. */
export default function QuotationPage({ client }: { client?: boolean }) {
  const { id = "", slug = "" } = useParams();
  const [params] = useSearchParams();
  const kind = params.get("kind") === "final" ? "final" : "draft";
  const { t } = useI18n();
  const [q, setQ] = useState<QuotationData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const token = (() => { try { return localStorage.getItem(`gj_trips_${slug}`); } catch { return null; } })();
  const load = () => {
    setError(null);
    const req = client
      ? get<QuotationData>(`/api/public/companies/${slug}/me/trips/${id}/quotation`, { customerToken: token })
      : get<QuotationData>(`/api/tickets/${id}/quotation?kind=${kind}`);
    req.then((x) => { setQ(x); document.title = `${x.reference} · ${x.company.name}`; }).catch((e) => setError((e as Error).message));
  };
  useEffect(load, [id, kind, client, slug]); // eslint-disable-line react-hooks/exhaustive-deps
  const back = client ? `/c/${slug}/me` : `/app/tickets?open=${id}`;
  return (
    <div className="qt-page">
      <div className="qt-tools no-print">
        <Link className="btn btn-ghost" to={back}><ArrowLeft className="flip" />{t("Back")}</Link>
        <span className="spacer" />
        <LangSwitch className="btn btn-ghost" />
        <button type="button" className="btn btn-primary" onClick={() => window.print()} disabled={!q}><Printer />{t("Print or save as PDF")}</button>
      </div>
      {q ? <QuotationSheet q={q} /> : <div style={{ maxWidth: 820, margin: "0 auto" }}>{error ? <ErrorBox error={error} onRetry={load} /> : <Loading height={320} />}</div>}
    </div>
  );
}
