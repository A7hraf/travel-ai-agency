import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { get, post } from "../../api";
import { useI18n } from "../../lang";
import { timeAgo } from "../../util";
import { Bell } from "../Icon";
import { Sheet } from "./Sheet";

interface Note { id: number; kind: string; params: Record<string, string>; ticket_id: number | null; read: boolean; created_at: string }

// The text of each kind, filled with its params (the server stores the facts, the screen writes the sentence).
const TEXT: Record<string, string> = {
  new_request: "New request {ref} from {client}",
  assigned: "{by} gave you request {ref}",
  client_answered: "{client} answered on {ref}",
  client_file: "{client} sent a file on {ref}",
  receipt: "{client} sent a payment receipt on {ref}",
  client_approved: "{client} approved the quotation of {ref}",
  client_cancelled: "{client} cancelled {ref}",
  step_late: "{ref} is late at “{step}” ({hours} h)",
  price_changed: "{by} changed the price of {ref}: {old} → {new}",
  reference_changed: "{by} changed the reference of {ref}: {old} → {new}",
  client_problem: "{client} has a problem on the trip {ref}: “{text}”",
  appointment_soon: "Soon: {title} · {when}",
  b2b_changes: "{client} asked for changes on {ref}: “{text}”",
  b2b_plan: "A payment plan was set on {ref}",
  b2b_payment_due: "Payment due on {ref}: {label} ({date})",
  b2b_payment_due_vendor: "Pay the vendor on {ref}: {label} ({date})",
};
const POLL_MS = 60_000;

export default function NotificationBell({ className = "" }: { className?: string }) {
  const { t, lang } = useI18n();
  const navigate = useNavigate();
  const [items, setItems] = useState<Note[]>([]);
  const [unread, setUnread] = useState(0);
  const [open, setOpen] = useState(false);

  const load = useCallback(() => {
    if (document.visibilityState === "hidden") return;
    get<{ unread: number; items: Note[] }>("/api/notifications", { quiet: true })
      .then((r) => { setItems(r.items); setUnread(r.unread); }).catch(() => {});
  }, []);
  useEffect(() => {
    load();
    const id = window.setInterval(load, POLL_MS);
    return () => window.clearInterval(id);
  }, [load]);

  const text = (n: Note) => {
    const p = { ...n.params, step: lang === "ar" ? n.params.step_ar || n.params.step : n.params.step };
    const kind = n.kind === "b2b_payment_due" && n.params.side === "vendor" ? "b2b_payment_due_vendor" : n.kind;
    return t(TEXT[kind] ?? kind, p);
  };
  const openOne = (n: Note) => {
    if (!n.read) post("/api/notifications/read", { ids: [n.id] }).then(load).catch(() => {});
    setOpen(false);
    if (n.ticket_id) navigate(`/app/tickets?open=${n.ticket_id}`);
    else if (n.params.b2b_id) navigate(`/app/requests/${n.params.b2b_id}`);
  };
  const readAll = () => post("/api/notifications/read", {}).then(load).catch(() => {});

  return (
    <>
      <button type="button" className={`gx-bell ${className}`} aria-label={unread ? t("Notifications: {n} new", { n: unread }) : t("Notifications")}
        aria-haspopup="dialog" aria-expanded={open} onClick={() => { setOpen(true); load(); }}>
        <Bell size={20} weight={unread ? "fill" : "regular"} aria-hidden="true" />
        {unread > 0 && <span className="gx-bell-count" aria-hidden="true">{unread > 99 ? "99+" : unread}</span>}
      </button>
      {open && (
        <Sheet label={t("Notifications")} onClose={() => setOpen(false)} className="gx-notes">
          <div className="gx-notes-head">
            <h3>{t("Notifications")}</h3>
            {unread > 0 && <button type="button" className="btn btn-ghost btn-sm" onClick={readAll}>{t("Mark all as read")}</button>}
          </div>
          {items.length === 0 ? <p className="muted">{t("Nothing new.")}</p> : (
            <ul className="gx-notes-list">
              {items.map((n) => (
                <li key={n.id}>
                  <button type="button" className={n.read ? "" : "unread"} onClick={() => openOne(n)}>
                    <span dir="auto">{text(n)}</span>
                    <small className="muted">{timeAgo(n.created_at)}</small>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Sheet>
      )}
    </>
  );
}
