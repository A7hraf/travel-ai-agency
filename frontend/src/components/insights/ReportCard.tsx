import { useState } from "react";
import { post } from "../../api";
import { useI18n } from "../../lang";
import { dateTime } from "../../util";
import { Sparkle } from "../Icon";
import { ErrorBox } from "../ui";
import Markdown from "./Markdown";

export interface Report { id: number; language: string; content: string; created_by: string | null; created_at: string }

/** The latest written analysis by the AI, with a button to write a new one in English or Arabic. */
export default function ReportCard({ report, path, title, note, onNew }: {
  report: Report | null; path: string; title: string; note: string; onNew: (r: Report) => void;
}) {
  const { t, lang } = useI18n();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const write = async (language: "en" | "ar") => {
    setBusy(true);
    setError(null);
    try { onNew(await post<Report>(path, { language })); } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  };
  return (
    <section className="gx-card gx-report">
      <div className="gx-row-between">
        <h2 className="gx-card-title"><Sparkle weight="fill" />{title}</h2>
        <div className="gx-inline gx-report-btns">
          <button className="btn btn-primary btn-sm" disabled={busy} onClick={() => write(lang === "ar" ? "ar" : "en")}>
            <Sparkle />{busy ? t("The AI is writing…") : report ? t("Write a new report") : t("Write my report")}
          </button>
          <button className="btn btn-ghost btn-sm" disabled={busy} onClick={() => write(lang === "ar" ? "en" : "ar")}>{lang === "ar" ? "English" : "بالعربية"}</button>
        </div>
      </div>
      <p className="gx-card-note">{note}</p>
      <ErrorBox error={error} />
      {report ? (<>
        <p className="muted small">{t("Written {date} by the AI for {name}", { date: dateTime(report.created_at), name: report.created_by ?? "—" })}</p>
        <Markdown text={report.content} />
      </>) : <p className="muted">{t("No report yet.")}</p>}
    </section>
  );
}
