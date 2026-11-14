import { useI18n } from "../../lang";
import type { Service, Ticket } from "../../types";
import { WarningCircle } from "../Icon";

/** The AI's request card: the service, the client's answers to its questions, and their last change request. */
export default function RequestCard({ ticket, services }: { ticket: Ticket; services: Service[] }) {
  const { t, lang } = useI18n();
  if (!ticket.service) return null;
  const service = services.find((s) => s.id === ticket.service!.id);
  const label = (key: string) => {
    const f = service?.fields.find((x) => x.key === key);
    return f ? (lang === "ar" ? f.label_ar : f.label_en) : key.replace(/_/g, " ");
  };
  const answers = Object.entries(ticket.answers ?? {});
  return (
    <section className="gx-rq-card" aria-label={t("Request card")}>
      <div className="gx-rq-card-head">
        <span className="gx-rq-service">{lang === "ar" ? ticket.service.name_ar : ticket.service.name_en}</span>
        {ticket.quote_round > 0 && <span className="muted small">{t("Quotation round {n}", { n: ticket.quote_round })}</span>}
      </div>
      {ticket.client_note && (
        <div className="gx-rq-note" role="note"><WarningCircle weight="fill" /><span><strong>{t("The client asked for changes:")}</strong> <span dir="auto">{ticket.client_note}</span></span></div>
      )}
      {answers.length > 0 && (
        <dl className="gx-rq-answers">
          {answers.map(([k, v]) => <div key={k}><dt>{label(k)}</dt><dd dir="auto">{v}</dd></div>)}
        </dl>
      )}
    </section>
  );
}
