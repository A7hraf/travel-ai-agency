import { trServer, useI18n } from "../../lang";
import type { TicketEvent } from "../../types";
import { dateTime, TICKET_STATUS_LABELS } from "../../util";
import { moneyText } from "../Money";

/** Status colours of the design (always shown with a text label). */
export const STATUS_COLOR: Record<string, string> = {
  new: "var(--st-progress)",
  quoted: "var(--st-paid)",
  changes: "var(--st-waiting)",
  chosen: "var(--st-progress)",
  final: "var(--st-paid)",
  rejected: "var(--st-cancelled)",
  pending_payment: "var(--st-waiting)",
  in_progress: "var(--st-progress)",
  paid: "var(--st-paid)",
  confirmed: "var(--st-confirmed)",
  cancelled: "var(--st-cancelled)",
};

export default function TicketHistory({ events, currency, lang }: { events: TicketEvent[] | null; currency: string; lang: "en" | "ar" }) {
  const { t } = useI18n();
  const status = (v: string | null) => (v && TICKET_STATUS_LABELS[v] ? t(TICKET_STATUS_LABELS[v]) : v ?? "—");
  const money = (v: string | null) => (v == null || v === "" || Number.isNaN(Number(v)) ? v ?? "—" : moneyText(Number(v), currency, lang));

  const describe = (ev: TicketEvent): string => {
    const who = ev.actor === "AI" ? t("AI agent") : ev.actor === "System" ? t("System")
      : ev.actor === "Client" ? t("The client") : ev.actor === "Client (trips page)" ? t("The client (trips page)") : ev.actor;
    switch (ev.action) {
      case "created":
        return ev.new_value
          ? t("{who} created the booking: {details}", { who, details: trServer(ev.new_value) })
          : t("{who} created the booking", { who });
      case "assigned":
        return ev.old_value
          ? t("{who} moved the ticket from {old} to {new}", { who, old: ev.old_value, new: ev.new_value ?? "—" })
          : t("{who} assigned the ticket to {new}", { who, new: ev.new_value ?? "—" });
      case "unassigned":
        return ev.old_value
          ? t("{who} removed {old} from the ticket", { who, old: ev.old_value })
          : t("{who} removed the assignment", { who });
      case "payment_reference":
        return ev.new_value
          ? t("{who} set the payment reference to {new}", { who, new: `⁦${ev.new_value}⁩` })
          : t("{who} removed the payment reference", { who });
      case "price":
        return t("{who} changed the price from {old} to {new}", { who, old: money(ev.old_value), new: money(ev.new_value) });
      case "status":
        return t("{who} changed the status from {old} to {new}", { who, old: status(ev.old_value), new: status(ev.new_value) });
      case "notes":
        return t("{who} updated the internal notes", { who });
      case "seats_released":
        return trServer(ev.new_value) || t("Seats released");
      case "option_added":
        return t("{who} added the choice {new}", { who, new: ev.new_value ?? "" });
      case "option_changed":
        return t("{who} changed the choice {new}", { who, new: ev.new_value ?? "" });
      case "option_removed":
        return t("{who} removed the choice {new}", { who, new: ev.new_value ?? "" });
      case "ai_drafted":
        return t("{who} let the AI draft choices ({new})", { who, new: ev.new_value ?? "" });
      case "chosen":
        return t("{who} picked: {new}", { who, new: ev.new_value ?? "" });
      case "changes":
        return t("{who} asked for changes: {new}", { who, new: ev.new_value ?? "" });
      case "final_note":
        return t("{who} added to the final quotation: {new}", { who, new: ev.new_value ?? "" });
      case "moved":
        return t("Moved from the old requests");
      case "payment_proof":
        return t("{who} sent a payment proof: {new}", { who, new: ev.new_value ?? "" });
      case "client_file":
        return t("{who} sent a file: {new}", { who, new: ev.new_value ?? "" });
      case "file_added":
        return t("{who} added the file {new}", { who, new: ev.new_value ?? "" });
      case "file_removed":
        return t("{who} removed the file {new}", { who, new: ev.new_value ?? "" });
      case "step_done":
        return t("{who} ticked: {new}", { who, new: ev.new_value ?? "" });
      case "step_undone":
        return t("{who} unticked: {new}", { who, new: ev.new_value ?? "" });
      case "saved_to_library":
        return t("{who} saved {new} to the library", { who, new: ev.new_value ?? "" });
      case "payment_added":
        return t("{who} recorded a payment: {new}", { who, new: ev.new_value ?? "" });
      case "payment_approved":
        return t("{who} approved a payment receipt: {new}", { who, new: ev.new_value ?? "" });
      case "payment_rejected":
        return t("{who} refused a payment receipt: {new}", { who, new: ev.new_value ?? "" });
      case "cost":
        return ev.new_value ? t("{who} set the cost to {new}", { who, new: money(ev.new_value) }) : t("{who} removed the cost", { who });
      case "details_changed":
        return t("{who} updated the request details", { who });
      case "plan_saved":
        return t("{who} saved the trip plan ({new})", { who, new: ev.new_value ?? "" });
      case "file_sorted":
        return t("{who} sorted a file: {new}", { who, new: ev.new_value ?? "" });
      case "documents_sent":
        return t("{who} sent the documents: {new}", { who, new: ev.new_value ?? "" });
      default:
        return `${who}: ${ev.action}`;
    }
  };
  const dot = (ev: TicketEvent) =>
    ev.action === "status" ? STATUS_COLOR[ev.new_value ?? ""] ?? "var(--brand)"
      : ev.action === "payment_reference" ? "var(--st-paid)"
        : ev.action === "price" ? "var(--accent)"
          : ev.action === "notes" || ev.action === "seats_released" ? "var(--st-cancelled)" : "var(--brand)";

  return (
    <section className="tk-history" aria-label={t("History")}>
      <h3>{t("History")}</h3>
      {events === null ? <div className="muted small">{t("Loading…")}</div> : events.length === 0 ? (
        <div className="muted small">{t("No changes yet.")}</div>
      ) : (
        <ol className="timeline">
          {[...events].reverse().map((ev) => (
            <li key={ev.id} style={{ ["--dot" as string]: dot(ev) }}>
              <span className="tl-rail" aria-hidden="true"><span className="tl-dot" /></span>
              <span className="tl-body">
                <span className="tl-text">{describe(ev)}</span>
                <span className="tl-time">{dateTime(ev.created_at)}</span>
              </span>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
