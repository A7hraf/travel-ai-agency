import { FormEvent, useEffect, useState } from "react";
import { del, get, patch, post } from "../api";
import { ConfirmSheet, initials, PageTitle, Switch } from "../components/admin/AdminUI";
import { Copy, Key, PencilSimple, Plus, Trash, WhatsappLogo } from "../components/Icon";
import { Empty, ErrorBox, Field, Loading, Modal } from "../components/ui";
import { useI18n } from "../lang";
import type { B2BOverview, Partner, PartnerKind, PartnerList, PartnerLogin } from "../types";
import { dateTime } from "../util";

const KIND_LABEL: Record<PartnerKind, { one: string; many: string; add: string; note: string }> = {
  client: { one: "Business client", many: "Business clients", add: "Add business client",
    note: "Companies that request travel for their people. Their logins see their own requests and history only." },
  vendor: { one: "Vendor", many: "Vendors", add: "Add vendor",
    note: "Supplier agencies that arrange flights, hotels, transport, food and activities for your trips." },
};

/** "96891234567" → "+968 9123 4567" style (country code first). */
export const showPhone = (digits: string) => `+${digits}`;

function PasswordOnce({ email, password, onDone }: { email: string; password: string; onDone: () => void }) {
  const { t } = useI18n();
  const [copied, setCopied] = useState(false);
  const copy = () => {
    navigator.clipboard?.writeText(`${email}\n${password}`).then(() => setCopied(true)).catch(() => {});
  };
  return (
    <div className="gx-once" role="status">
      <strong>{t("Save this password now: it is shown only once.")}</strong>
      <div className="gx-once-row">
        <bdi dir="ltr">{email}</bdi>
        <code dir="ltr">{password}</code>
        <button type="button" className="btn btn-sm btn-soft" onClick={copy}><Copy />{copied ? t("Copied") : t("Copy")}</button>
      </div>
      <p className="muted small">{t("Send it to the person privately. They sign in on the normal login page.")}</p>
      <button type="button" className="btn btn-sm" onClick={onDone}>{t("Done")}</button>
    </div>
  );
}

function Logins({ partner, max, onChanged }: { partner: Partner; max: number; onChanged: () => void }) {
  const { t } = useI18n();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [shown, setShown] = useState<{ email: string; password: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [removing, setRemoving] = useState<PartnerLogin | null>(null);
  const base = `/api/partners/${partner.id}/logins`;
  const active = partner.logins.filter((l) => l.is_active).length;

  const run = async (fn: () => Promise<void>) => {
    setError(null);
    setBusy(true);
    try { await fn(); onChanged(); } catch (err) { setError((err as Error).message); } finally { setBusy(false); }
  };
  const add = (e: FormEvent) => {
    e.preventDefault();
    run(async () => {
      const r = await post<{ login: PartnerLogin; password: string }>(base, { full_name: name, email });
      setShown({ email: r.login.email, password: r.password });
      setName(""); setEmail("");
    });
  };
  const newPassword = (l: PartnerLogin) => run(async () => {
    const r = await patch<{ login: PartnerLogin; password: string }>(`${base}/${l.id}`, { new_password: true });
    setShown({ email: r.login.email, password: r.password });
  });

  return (
    <section className="gx-logins" aria-label={t("Logins")}>
      <div className="field-label">{t("Logins")} <span className="muted">{active} / {max}</span></div>
      {shown && <PasswordOnce {...shown} onDone={() => setShown(null)} />}
      {partner.logins.length === 0 && <p className="muted small">{t("No logins yet. Add one so this account can sign in.")}</p>}
      <ul className="gx-login-list">
        {partner.logins.map((l) => (
          <li key={l.id} className={l.is_active ? "" : "off"}>
            <div className="gx-login-who">
              <span dir="auto">{l.full_name}</span>
              <bdi dir="ltr" className="muted small">{l.email}</bdi>
              <span className="muted small">{t("Last login")}: {dateTime(l.last_login_at)}</span>
            </div>
            <Switch checked={l.is_active} disabled={busy || (!l.is_active && active >= max)}
              onChange={(v) => run(async () => { await patch(`${base}/${l.id}`, { is_active: v }); })}
              label={l.is_active ? t("Active") : t("Disabled")} />
            <button type="button" className="btn btn-sm btn-soft" disabled={busy} onClick={() => newPassword(l)}><Key />{t("New password")}</button>
            <button type="button" className="icon-btn" disabled={busy} onClick={() => setRemoving(l)} aria-label={t("Delete {name}", { name: l.full_name })}><Trash /></button>
          </li>
        ))}
      </ul>
      <form className="gx-login-add" onSubmit={add}>
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder={t("Full name")} aria-label={t("Full name")} required maxLength={200} dir="auto" />
        <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder={t("Email (login)")} aria-label={t("Email (login)")} required dir="ltr" />
        <button className="btn btn-soft" disabled={busy || active >= max}><Plus />{t("Add login")}</button>
      </form>
      {active >= max && <p className="muted small">{t("Login limit reached for this account. The platform admin can raise it.")}</p>}
      <ErrorBox error={error} />
      {removing && (
        <ConfirmSheet title={t("Delete the login of {name}?", { name: removing.full_name })} text={t("This can't be undone.")}
          tone="danger" busy={busy} confirmLabel={t("Delete")}
          onConfirm={() => { const l = removing; setRemoving(null); run(async () => { await del(`${base}/${l.id}`); }); }}
          onCancel={() => setRemoving(null)} />
      )}
    </section>
  );
}

function PartnerForm({ kind, partner, overview, onClose, onSaved }: {
  kind: PartnerKind; partner: Partner | null; overview: B2BOverview; onClose: () => void;
  /** Reload the list, then keep this account open (id) or close the form (null). */
  onSaved: (next: number | null) => void;
}) {
  const { t } = useI18n();
  const [name, setName] = useState(partner?.name ?? "");
  const [contactName, setContactName] = useState(partner?.contact_name ?? "");
  const [contactEmail, setContactEmail] = useState(partner?.contact_email ?? "");
  const [contactPhone, setContactPhone] = useState(partner?.contact_phone ?? "");
  const [notes, setNotes] = useState(partner?.notes ?? "");
  const [features, setFeatures] = useState<string[]>(partner?.features ?? []);
  const [numbers, setNumbers] = useState((partner?.whatsapp_numbers ?? []).map(showPhone).join("\n"));
  const [active, setActive] = useState(partner?.is_active ?? true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const allowed = new Set(overview.settings.features);
  const kindFeatures = Object.keys(overview.catalog).filter((f) => f.startsWith(`${kind}.`));
  const toggle = (f: string) => setFeatures(features.includes(f) ? features.filter((x) => x !== f) : [...features, f]);

  const save = async (e: FormEvent) => {
    e.preventDefault();
    if (busy) return;
    setError(null);
    setBusy(true);
    const body = {
      name, contact_name: contactName, contact_email: contactEmail || null, contact_phone: contactPhone, notes,
      features, is_active: active,
      ...(kind === "client" ? { whatsapp_numbers: numbers.split(/[\n,]+/).map((x) => x.trim()).filter(Boolean) } : {}),
    };
    try {
      const saved = partner ? await patch<Partner>(`/api/partners/${partner.id}`, body) : await post<Partner>("/api/partners", { kind, ...body });
      onSaved(partner ? null : saved.id);  // a new account stays open so logins can be added
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const remove = async () => {
    if (!partner) return;
    setBusy(true);
    try { await del(`/api/partners/${partner.id}`); onSaved(null); } catch (err) { setError((err as Error).message); setConfirmDelete(false); } finally { setBusy(false); }
  };

  return (
    <Modal title={partner ? t("Edit {name}", { name: partner.name }) : t(KIND_LABEL[kind].add)} onClose={onClose} wide>
      <form onSubmit={save}>
        <div className="form-grid">
          <Field label={t("Name")}><input value={name} onChange={(e) => setName(e.target.value)} required minLength={2} maxLength={200} dir="auto" /></Field>
          <Field label={t("Contact person")}><input value={contactName} onChange={(e) => setContactName(e.target.value)} maxLength={200} dir="auto" /></Field>
          <Field label={t("Contact email")}><input type="email" value={contactEmail} onChange={(e) => setContactEmail(e.target.value)} dir="ltr" /></Field>
          <Field label={t("Contact phone")}><input value={contactPhone} onChange={(e) => setContactPhone(e.target.value)} maxLength={50} dir="ltr" /></Field>
        </div>
        {kind === "client" && (
          <Field label={t("WhatsApp numbers of this business")} hint={t("One per line, with the country code. Messages from these numbers are known to come from this business.")}>
            <textarea rows={3} value={numbers} onChange={(e) => setNumbers(e.target.value)} dir="ltr" placeholder="+968 9123 4567" />
          </Field>
        )}
        <div className="field-label">{t("Features")}</div>
        <div className="perm-grid">
          {kindFeatures.map((f) => {
            const ok = allowed.has(f);
            return (
              <label key={f} className={`perm ${ok ? "" : "perm-locked"} ${features.includes(f) ? "on" : ""}`}
                title={ok ? undefined : t("Not allowed by the platform admin")}>
                <input type="checkbox" checked={features.includes(f)} disabled={!ok && !features.includes(f)} onChange={() => toggle(f)} />
                <span>{t(overview.catalog[f])}{!ok && <em className="muted small"> · {t("Not allowed by the platform admin")}</em>}</span>
              </label>
            );
          })}
        </div>
        <Field label={t("Internal notes")}><textarea rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} maxLength={2000} dir="auto" /></Field>
        {partner && <Switch checked={active} onChange={setActive} label={t("Account active (its logins can sign in)")} />}
        <ErrorBox error={error} />
        <div className="modal-actions">
          {partner && <button type="button" className="btn btn-danger" disabled={busy} onClick={() => setConfirmDelete(true)}><Trash />{t("Delete")}</button>}
          <span className="spacer" />
          <button type="button" className="btn btn-ghost" onClick={onClose}>{t("Cancel")}</button>
          <button className="btn btn-primary" disabled={busy}>{busy ? t("Saving…") : partner ? t("Save") : t("Create")}</button>
        </div>
      </form>
      {partner && <Logins partner={partner} max={overview.settings.max_users_per_partner} onChanged={() => onSaved(partner.id)} />}
      {confirmDelete && partner && (
        <ConfirmSheet title={t("Delete {name}?", { name: partner.name })} text={t("Its logins are deleted too. This can't be undone.")}
          tone="danger" busy={busy} confirmLabel={t("Delete")} onConfirm={remove} onCancel={() => setConfirmDelete(false)} />
      )}
    </Modal>
  );
}

export default function Partners() {
  const { t } = useI18n();
  const [data, setData] = useState<PartnerList | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [kind, setKind] = useState<PartnerKind>("client");
  const [editing, setEditing] = useState<number | "new" | null>(null);
  const load = () => get<PartnerList>("/api/partners").then((d) => { setData(d); setError(null); }).catch((e) => setError((e as Error).message));
  useEffect(() => { load(); }, []);

  const head = <PageTitle kicker={t("Agency workspace")} title={t("Business accounts")}
    subtitle={t("Business clients who request travel, and the vendors who arrange it. You are the link between them.")} />;
  if (!data) return <div>{head}{error ? <ErrorBox error={error} onRetry={load} /> : <Loading height={240} />}</div>;

  const { settings, usage } = data;
  const used = kind === "client" ? usage.clients : usage.vendors;
  const max = kind === "client" ? settings.max_clients : settings.max_vendors;
  const list = data.partners.filter((p) => p.kind === kind);
  const current = typeof editing === "number" ? data.partners.find((p) => p.id === editing) ?? null : null;

  return (
    <div>
      {head}
      <div className="gx-b2b-meters">
        {(["client", "vendor"] as PartnerKind[]).map((k) => {
          const u = k === "client" ? usage.clients : usage.vendors;
          const m = k === "client" ? settings.max_clients : settings.max_vendors;
          return (
            <div key={k} className="gx-b2b-meter">
              <div className="gx-b2b-num tnum">{u}<span className="muted"> / {m}</span></div>
              <div className="muted small">{t(KIND_LABEL[k].many)}</div>
              <div className={`tm-meter ${u >= m ? "full" : ""}`}><div style={{ width: `${Math.min(100, (u / Math.max(1, m)) * 100)}%` }} /></div>
            </div>
          );
        })}
        <div className="gx-b2b-meter">
          <div className="gx-b2b-num tnum">{settings.max_users_per_partner}</div>
          <div className="muted small">{t("Logins per account")}</div>
        </div>
      </div>

      <div className="gx-b2b-bar">
        <div className="seg" role="tablist" aria-label={t("Business accounts")}>
          {(["client", "vendor"] as PartnerKind[]).map((k) => (
            <button key={k} type="button" role="tab" aria-selected={kind === k} className={kind === k ? "active" : ""} onClick={() => setKind(k)}>{t(KIND_LABEL[k].many)}</button>
          ))}
        </div>
        <span className="spacer" />
        <button className="btn btn-primary" disabled={used >= max} onClick={() => setEditing("new")}><Plus weight="bold" />{t(KIND_LABEL[kind].add)}</button>
      </div>
      <p className="muted small">{t(KIND_LABEL[kind].note)}{used >= max && ` ${t("Limit reached. The platform admin can raise it.")}`}</p>

      {list.length === 0 ? <Empty>{t("None yet.")}</Empty> : (
        <ul className="tm-list">
          {list.map((p) => (
            <li key={p.id} className={`tm-row ${p.is_active ? "" : "off"}`}>
              <span className="tm-avatar" aria-hidden="true">{initials(p.name)}</span>
              <div className="tm-who">
                <div className="tm-name" dir="auto">{p.name}</div>
                <span className="tm-email" dir="auto">{[p.contact_name, p.contact_email].filter(Boolean).join(" · ") || "—"}</span>
              </div>
              <div className="tm-role">
                <span className="gx-status cyan plain">{t("{n} features", { n: p.active_features.length })}</span>
                {p.whatsapp_numbers.length > 0 && <span className="tm-perms"><WhatsappLogo /> {p.whatsapp_numbers.length}</span>}
              </div>
              <div className="tm-state">
                {p.is_active ? <span className="gx-status on">{t("Active")}</span> : <span className="gx-status off">{t("Paused")}</span>}
                <span className="tm-login">{t("{n} logins", { n: p.logins.length })}</span>
              </div>
              <div className="tm-action">
                <button className="btn btn-sm btn-soft" onClick={() => setEditing(p.id)} aria-label={t("Edit {name}", { name: p.name })}><PencilSimple />{t("Edit")}</button>
              </div>
            </li>
          ))}
        </ul>
      )}

      {editing !== null && (editing === "new" || current) && (
        <PartnerForm key={editing} kind={current?.kind ?? kind} partner={current} overview={data}
          onClose={() => setEditing(null)}
          onSaved={(next) => { load(); setEditing(next); }} />
      )}
    </div>
  );
}
