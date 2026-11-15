import { FormEvent, useState } from "react";
import { put } from "../../api";
import { useAuth } from "../../auth";
import { useI18n } from "../../lang";
import type { Ticket } from "../../types";
import { PencilSimple } from "../Icon";
import { moneyText } from "../Money";
import { ErrorBox } from "../ui";

/** Price, cost, profit and payments of a request at a glance; staff set the price and the cost here. */
export default function MoneyBox({ ticket, onChange }: { ticket: Ticket; onChange: (t: Ticket) => void }) {
  const { t, lang } = useI18n();
  const { user, can } = useAuth();
  const m = ticket.money;
  const [edit, setEdit] = useState(false);
  const [price, setPrice] = useState("");
  const [cost, setCost] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const money = (v: number | null | undefined) => (v == null ? "—" : moneyText(v, ticket.currency, lang));
  const closed = ticket.stage === "closed";
  const paidStage = ticket.status === "paid" || ticket.status === "confirmed";
  const canPrice = can("tickets.manage") && !closed && (!paidStage || user?.role === "company_admin")
    && !(ticket.service?.key === "packages" && user?.role !== "company_admin");
  const price0 = m.total > 0 ? m.total : m.choices_total;
  const open = () => { setPrice(m.total > 0 ? String(m.total) : ""); setCost(ticket.cost_price != null ? String(ticket.cost_price) : ""); setEdit(true); };
  const save = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true); setError(null);
    const body: Record<string, unknown> = {};
    if (canPrice && price.trim() !== "" && Number(price) !== m.total) body.total_price = price.trim();
    if (cost.trim() === "" && ticket.cost_price != null) body.clear_cost = true;
    else if (cost.trim() !== "" && Number(cost) !== ticket.cost_price) body.cost_price = cost.trim();
    try { if (Object.keys(body).length) onChange(await put<Ticket>(`/api/tickets/${ticket.id}/money`, body)); setEdit(false); }
    catch (err) { setError((err as Error).message); } finally { setBusy(false); }
  };
  const profitTone = m.profit == null ? "" : m.profit < 0 ? "neg" : "pos";
  return (
    <section className="rw-card rw-money" aria-label={t("Money")}>
      <div className="rw-card-head">
        <h3>{t("Money")}</h3>
        {can("tickets.manage") && !edit && !closed && <button type="button" className="icon-btn" aria-label={t("Edit price and cost")} onClick={open}><PencilSimple /></button>}
      </div>
      {edit ? (
        <form onSubmit={save} className="rw-money-form">
          <label>{t("Client price")}
            <input value={price} onChange={(e) => setPrice(e.target.value)} inputMode="decimal" dir="ltr" disabled={!canPrice}
              placeholder={m.choices_total ? String(m.choices_total) : "0"} />
          </label>
          <label>{t("Our cost")}
            <input value={cost} onChange={(e) => setCost(e.target.value)} inputMode="decimal" dir="ltr"
              placeholder={m.cost_from === "choices" ? `${m.cost} (${t("from the choices")})` : t("e.g. what the suppliers charge")} />
          </label>
          <ErrorBox error={error} />
          <div className="rw-row-end">
            <button type="button" className="btn btn-sm btn-ghost" onClick={() => setEdit(false)}>{t("Cancel")}</button>
            <button className="btn btn-sm btn-primary" disabled={busy}>{t("Save")}</button>
          </div>
        </form>
      ) : (
        <dl className="rw-money-grid">
          <dt>{t("Client price")}</dt>
          <dd className="rw-strong">{price0 ? money(price0) : <span className="muted">{t("Not priced yet")}</span>}
            {m.total === 0 && m.choices_total > 0 && <span className="muted small"> · {t("chosen so far")}</span>}</dd>
          <dt>{t("Our cost")}</dt>
          <dd>{m.cost == null ? <span className="muted">{t("Not written")}</span> : money(m.cost)}
            {m.cost_from === "choices" && <span className="muted small"> · {t("from the choices")}</span>}</dd>
          <dt>{t("Profit")}</dt>
          <dd className={`rw-profit ${profitTone}`}>{m.profit == null ? "—" : <>{money(m.profit)}{m.margin_pct != null && <span className="small"> · {m.margin_pct}%</span>}</>}</dd>
          {(m.paid > 0 || ["payment", "booking", "confirmed"].includes(ticket.stage)) && (
            <>
              <dt>{t("Paid")}</dt><dd>{money(m.paid)}</dd>
              <dt>{t("Balance")}</dt><dd className={m.balance ? "rw-due" : ""}>{money(m.balance ?? 0)}</dd>
            </>
          )}
        </dl>
      )}
      {!edit && m.cost == null && !closed && <p className="muted small rw-hint">{t("Write the cost on each choice, or here, to see the profit.")}</p>}
    </section>
  );
}
