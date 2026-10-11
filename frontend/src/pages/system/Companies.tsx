import { FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { get, post } from "../../api";
import { Badge, Empty, ErrorBox, Field, Modal, PageHeader } from "../../components/ui";
import type { CompanyAdmin, PlatformStats } from "../../types";
import { shortDate } from "../../util";

export default function Companies() {
  const [companies, setCompanies] = useState<CompanyAdmin[] | null>(null);
  const [stats, setStats] = useState<PlatformStats | null>(null);
  const [creating, setCreating] = useState(false);

  const load = () => {
    get<CompanyAdmin[]>("/api/system/companies").then(setCompanies).catch(() => {});
    get<PlatformStats>("/api/system/stats").then(setStats).catch(() => {});
  };
  useEffect(load, []);

  return (
    <div>
      <PageHeader title="Travel companies" subtitle="Every company has its own accounts, packages and customers, served by the same AI brain."
        actions={<button className="btn btn-primary" onClick={() => setCreating(true)}>+ New company</button>} />
      {stats && (
        <div className="stats">
          <div className="stat"><div className="stat-label">Companies</div><div className="stat-value">{stats.active_companies}<span className="stat-of"> / {stats.companies} active</span></div></div>
          <div className="stat"><div className="stat-label">Employee accounts</div><div className="stat-value">{stats.users}</div></div>
          <div className="stat"><div className="stat-label">Conversations</div><div className="stat-value">{stats.conversations}</div></div>
          <div className="stat"><div className="stat-label">Booking tickets</div><div className="stat-value">{stats.tickets}</div></div>
        </div>
      )}
      {companies === null ? <div className="loading">Loading…</div> : companies.length === 0 ? <Empty>No companies yet.</Empty> : (
        <div className="table-wrap">
          <table className="table">
            <thead><tr><th>Company</th><th>Status</th><th>Accounts</th><th>Packages</th><th>Open tickets</th><th>WhatsApp</th><th>Created</th><th /></tr></thead>
            <tbody>
              {companies.map((c) => (
                <tr key={c.id}>
                  <td><strong>{c.name}</strong><div className="muted small">/c/{c.slug}</div></td>
                  <td>{c.status === "active" ? <Badge tone="green">Active</Badge> : <Badge tone="red">Suspended</Badge>}</td>
                  <td>{c.user_count} / {c.max_users}</td>
                  <td>{c.package_count}</td>
                  <td>{c.open_tickets}</td>
                  <td>{c.whatsapp_connected ? "Connected" : <span className="muted">—</span>}</td>
                  <td className="small muted">{shortDate(c.created_at)}</td>
                  <td><Link className="btn btn-sm" to={`/system/companies/${c.id}`}>Manage</Link></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {creating && <CreateCompany onClose={() => setCreating(false)} onCreated={() => { setCreating(false); load(); }} />}
    </div>
  );
}

function CreateCompany({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const [f, setF] = useState({ name: "", slug: "", max_users: "5", currency: "USD", contact_email: "",
    admin_full_name: "", admin_email: "", admin_password: "" });
  const [error, setError] = useState<string | null>(null);
  const set = (k: keyof typeof f, v: string) => setF({ ...f, [k]: v });

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      await post("/api/system/companies", {
        ...f, slug: f.slug.trim() || null, contact_email: f.contact_email.trim() || null, max_users: Number(f.max_users),
      });
      onCreated();
    } catch (err) {
      setError((err as Error).message);
    }
  };

  return (
    <Modal title="New travel company" onClose={onClose} wide>
      <form onSubmit={submit}>
        <div className="form-grid">
          <Field label="Company name"><input value={f.name} onChange={(e) => set("name", e.target.value)} required /></Field>
          <Field label="Web address (slug)" hint="Optional. Customer page: /c/your-slug">
            <input value={f.slug} placeholder="auto from name" onChange={(e) => set("slug", e.target.value.toLowerCase())} />
          </Field>
          <Field label="Account limit" hint="How many employee accounts this company may create (admin included).">
            <input type="number" min={1} value={f.max_users} onChange={(e) => set("max_users", e.target.value)} required />
          </Field>
          <Field label="Currency"><input maxLength={3} value={f.currency} onChange={(e) => set("currency", e.target.value.toUpperCase())} required /></Field>
          <Field label="Contact email"><input type="email" value={f.contact_email} onChange={(e) => set("contact_email", e.target.value)} /></Field>
        </div>
        <h3>First company admin</h3>
        <div className="form-grid">
          <Field label="Full name"><input value={f.admin_full_name} onChange={(e) => set("admin_full_name", e.target.value)} required /></Field>
          <Field label="Email (login)"><input type="email" value={f.admin_email} onChange={(e) => set("admin_email", e.target.value)} required /></Field>
          <Field label="Temporary password" hint="At least 8 characters. Ask them to change it."><input minLength={8} value={f.admin_password} onChange={(e) => set("admin_password", e.target.value)} required /></Field>
        </div>
        <ErrorBox error={error} />
        <div className="modal-actions"><span className="spacer" />
          <button type="button" className="btn btn-ghost" onClick={onClose}>Cancel</button>
          <button className="btn btn-primary">Create company</button>
        </div>
      </form>
    </Modal>
  );
}
