import { FormEvent, ReactNode, useState } from "react";
import { useI18n } from "../../lang";
import type { Amount, TripMessage, TripPart, TripStatus, TripStep } from "../../types";
import { dateTime, shortDate } from "../../util";
import { moneyText } from "../Money";
import { ErrorBox } from "../ui";
import { Bed, Car, ForkKnife, PaperPlaneRight, PersonSimpleHike, AirplaneTilt } from "../Icon";

export const PARTS: TripPart[] = ["flight", "hotel", "transport", "activity", "food"];
export const PART_LABEL: Record<TripPart, string> = {
  flight: "Flight", hotel: "Hotel", transport: "Transport", activity: "Activities", food: "Food",
};
export const PART_ICON = { flight: AirplaneTilt, hotel: Bed, transport: Car, activity: PersonSimpleHike, food: ForkKnife };

/** Status names: the same request reads differently for the travel company, the client and the vendor. */
export const STATUS: Record<TripStatus, { staff: string; client: string; vendor: string; tone: string }> = {
  new: { staff: "New", client: "Received", vendor: "New", tone: "warn" },
  with_vendor: { staff: "With vendor", client: "Finding options", vendor: "Waiting for your options", tone: "cyan" },
  options_ready: { staff: "Options to review", client: "Finding options", vendor: "Options sent", tone: "warn" },
  with_client: { staff: "Waiting for the client", client: "Choose your options", vendor: "Options sent", tone: "cyan" },
  chosen: { staff: "Client chose: approve", client: "Waiting for approval", vendor: "Options sent", tone: "warn" },
  approved: { staff: "Approved: to book", client: "Approved", vendor: "Approved: please book", tone: "cyan" },
  booked: { staff: "Booked", client: "Booked", vendor: "Booked", tone: "on" },
  completed: { staff: "Completed", client: "Completed", vendor: "Completed", tone: "on" },
  cancelled: { staff: "Cancelled", client: "Cancelled", vendor: "Cancelled", tone: "off" },
};

export const STEP_LABEL: Record<string, string> = {
  created: "Request sent", assigned: "Sent to you", accepted: "Accepted", declined: "Declined",
  options_submitted: "Options sent", sent_to_client: "Options ready", chosen: "Choice made", approved: "Approved",
  booked: "Booked", completed: "Completed", cancelled: "Cancelled", option_added: "Option added",
  option_changed: "Option changed", option_removed: "Option removed", markup: "Margin changed",
};

export function StatusBadge({ status, side }: { status: TripStatus; side: "staff" | "client" | "vendor" }) {
  const { t } = useI18n();
  const s = STATUS[status];
  return <span className={`gx-status ${s.tone}`}>{t(s[side])}</span>;
}

export function money(value: Amount, currency: string, lang: "en" | "ar"): string {
  return value === null || value === undefined || value === "" ? "—" : moneyText(Number(value), currency, lang);
}

export function PartChip({ part }: { part: TripPart }) {
  const { t } = useI18n();
  const Icon = PART_ICON[part];
  return <span className="gx-part"><Icon />{t(PART_LABEL[part])}</span>;
}

/** Destination, dates, travellers and the parts asked for. */
export function TripFacts({ trip, extra }: {
  trip: { origin: string | null; destination: string; depart_date: string | null; return_date: string | null; travellers: number; needs: TripPart[]; purpose: string | null };
  extra?: ReactNode;
}) {
  const { t } = useI18n();
  return (
    <dl className="gx-facts">
      <div><dt>{t("Route")}</dt><dd dir="auto">{trip.origin ? `${trip.origin} → ` : ""}{trip.destination}</dd></div>
      <div><dt>{t("Dates")}</dt><dd>{shortDate(trip.depart_date)}{trip.return_date ? ` – ${shortDate(trip.return_date)}` : ""}</dd></div>
      <div><dt>{t("Travellers")}</dt><dd>{trip.travellers}</dd></div>
      {trip.purpose && <div><dt>{t("Purpose")}</dt><dd dir="auto">{trip.purpose}</dd></div>}
      <div className="gx-facts-wide"><dt>{t("Needs")}</dt><dd className="gx-parts">{trip.needs.map((p) => <PartChip key={p} part={p} />)}</dd></div>
      {extra}
    </dl>
  );
}

export function Steps({ steps }: { steps: TripStep[] }) {
  const { t } = useI18n();
  if (!steps.length) return null;
  return (
    <ol className="gx-steps">
      {steps.map((s, i) => <li key={i}><span>{t(STEP_LABEL[s.action] ?? s.action)}</span><time>{dateTime(s.created_at)}</time></li>)}
    </ol>
  );
}

/** One conversation thread of a request, with a box to write. */
export function Thread({ messages, onSend, me, placeholder, disabled }: {
  messages: TripMessage[]; onSend: (text: string) => Promise<void>;
  /** author_kind of the person looking (their messages are on the other side). */
  me: string; placeholder?: string; disabled?: boolean;
}) {
  const { t } = useI18n();
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const send = async (e: FormEvent) => {
    e.preventDefault();
    if (!text.trim() || busy) return;
    setBusy(true);
    setError(null);
    try { await onSend(text.trim()); setText(""); } catch (err) { setError((err as Error).message); } finally { setBusy(false); }
  };
  return (
    <div className="gx-thread">
      {messages.length === 0 && <p className="muted small">{t("No messages yet.")}</p>}
      {messages.map((m) => (
        <div key={m.id} className={`gx-msg ${m.author_kind === me ? "mine" : ""}`}>
          <div className="gx-msg-who">{m.author_name ?? ""} · <time>{dateTime(m.created_at)}</time></div>
          <div className="gx-msg-text" dir="auto">{m.text}</div>
        </div>
      ))}
      {!disabled && (
        <form className="gx-thread-form" onSubmit={send}>
          <input value={text} onChange={(e) => setText(e.target.value)} maxLength={2000} dir="auto"
            placeholder={placeholder ?? t("Write a message…")} aria-label={t("Message")} />
          <button className="btn btn-soft" disabled={busy || !text.trim()} aria-label={t("Send")}><PaperPlaneRight className="flip" /></button>
        </form>
      )}
      <ErrorBox error={error} />
    </div>
  );
}
