import { useState } from "react";
import { Link } from "react-router-dom";
import { get } from "../api";
import { useAuth } from "../auth";
import { Badge, CONVERSATION_TONES, PageHeader, TICKET_TONES } from "../components/ui";
import type { Dashboard as DashboardData } from "../types";
import { Money } from "../components/Money";
import { CONVERSATION_STATUS_LABELS, TICKET_STATUS_LABELS, usePolling } from "../util";

export default function Dashboard() {
  const { user } = useAuth();
  const [data, setData] = useState<DashboardData | null>(null);
  usePolling(() => { get<DashboardData>("/api/dashboard").then(setData).catch(() => {}); }, 15000);

  if (!data) return <div className="loading">Loading…</div>;
  const openTickets = (data.tickets_by_status.pending_payment ?? 0) + (data.tickets_by_status.in_progress ?? 0)
    + (data.tickets_by_status.paid ?? 0);

  return (
    <div>
      <PageHeader title={`Welcome, ${user?.full_name.split(" ")[0]}`} subtitle="What's happening at your agency right now." />

      <div className="stats">
        <Link to="/app/conversations?status=human" className="stat stat-link">
          <div className="stat-label">Chats waiting for a human</div>
          <div className={`stat-value ${data.conversations_waiting ? "warn" : ""}`}>{data.conversations_waiting}</div>
        </Link>
        <Link to="/app/tickets" className="stat stat-link">
          <div className="stat-label">Open booking tickets</div>
          <div className="stat-value">{openTickets}</div>
          <div className="stat-sub"><Money value={data.pipeline_value} currency={data.currency} /> to collect</div>
        </Link>
        <div className="stat">
          <div className="stat-label">Confirmed sales</div>
          <div className="stat-value"><Money value={data.confirmed_value} currency={data.currency} /></div>
        </div>
        <div className="stat">
          <div className="stat-label">My open tickets</div>
          <div className="stat-value">{data.my_open_tickets}</div>
        </div>
        <div className="stat">
          <div className="stat-label">Active packages</div>
          <div className="stat-value">{data.packages_active}</div>
        </div>
        <div className="stat">
          <div className="stat-label">Team accounts</div>
          <div className="stat-value">{data.users}<span className="stat-of"> / {data.max_users}</span></div>
        </div>
      </div>

      <div className="grid-2">
        <section className="card">
          <h3>Conversations</h3>
          {Object.keys(CONVERSATION_STATUS_LABELS).map((s) => (
            <div className="row-between" key={s}>
              <Badge tone={CONVERSATION_TONES[s]}>{CONVERSATION_STATUS_LABELS[s]}</Badge>
              <strong>{data.conversations_by_status[s] ?? 0}</strong>
            </div>
          ))}
        </section>
        <section className="card">
          <h3>Booking tickets</h3>
          {Object.keys(TICKET_STATUS_LABELS).map((s) => (
            <div className="row-between" key={s}>
              <Badge tone={TICKET_TONES[s]}>{TICKET_STATUS_LABELS[s]}</Badge>
              <strong>{data.tickets_by_status[s] ?? 0}</strong>
            </div>
          ))}
        </section>
      </div>
    </div>
  );
}
