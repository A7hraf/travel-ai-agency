import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { ApiError, get, post } from "../api";
import { ChatText, Modal } from "../components/ui";
import type { PublicCompany, PublicMessage, TravelPackage } from "../types";
import { gradientFor, money, shortDate } from "../util";

export default function Storefront() {
  const { slug = "" } = useParams();
  const [company, setCompany] = useState<PublicCompany | null>(null);
  const [packages, setPackages] = useState<TravelPackage[]>([]);
  const [notFound, setNotFound] = useState(false);
  const [query, setQuery] = useState("");
  const [budget, setBudget] = useState("");
  const [selected, setSelected] = useState<TravelPackage | null>(null);
  const [chatOpen, setChatOpen] = useState(false);
  const [prefill, setPrefill] = useState<string | null>(null);

  useEffect(() => {
    get<PublicCompany>(`/api/public/companies/${slug}`).then((c) => {
      setCompany(c);
      document.title = `${c.name} · Travel packages`;
    }).catch(() => setNotFound(true));
    get<TravelPackage[]>(`/api/public/companies/${slug}/packages`).then(setPackages).catch(() => {});
  }, [slug]);

  if (notFound) return <div className="sf-missing">This travel agency page does not exist.</div>;
  if (!company) return <div className="loading-screen">Loading…</div>;

  const shown = packages.filter((p) => {
    const text = `${p.title} ${p.destination} ${p.country} ${p.tags.join(" ")} ${p.description}`.toLowerCase();
    return (!query || text.includes(query.toLowerCase())) && (!budget || p.price_per_person <= Number(budget));
  });

  const askAbout = (p: TravelPackage) => {
    setSelected(null);
    setPrefill(`Hi! I'm interested in the "${p.title}" package (${p.duration_days} days). Can you tell me more?`);
    setChatOpen(true);
  };
  const waDigits = company.whatsapp_number?.replace(/\D/g, "");

  return (
    <div className="sf">
      <header className="sf-hero">
        <div className="sf-nav">
          <div className="sf-logo">✈ {company.name}</div>
          <div className="sf-contact">
            {company.contact_phone && <span>☎ {company.contact_phone}</span>}
            {waDigits && <a className="btn btn-wa btn-sm" href={`https://wa.me/${waDigits}`} target="_blank" rel="noreferrer">WhatsApp us</a>}
          </div>
        </div>
        <div className="sf-hero-text">
          <h1>Where do you want to go next?</h1>
          <p>Browse our packages or chat with {company.ai_agent_name}, our AI travel consultant. Available 24/7, in your language.</p>
          <div className="sf-search">
            <input placeholder="Destination, country or trip type (beach, honeymoon, family…)" value={query} onChange={(e) => setQuery(e.target.value)} />
            <input type="number" min={0} placeholder={`Max budget (${company.currency})`} value={budget} onChange={(e) => setBudget(e.target.value)} />
            <button className="btn btn-primary" onClick={() => setChatOpen(true)}>Chat with {company.ai_agent_name}</button>
          </div>
        </div>
      </header>

      <main className="sf-main">
        <h2>Our offers</h2>
        {shown.length === 0 ? (
          <p className="muted">No package matches your search. <button className="link-btn" onClick={() => setChatOpen(true)}>Ask {company.ai_agent_name}</button> for a custom trip.</p>
        ) : (
          <div className="pkg-grid">
            {shown.map((p) => (
              <article key={p.id} className="pkg-card sf-card" onClick={() => setSelected(p)}>
                <div className="pkg-cover" style={{ background: p.image_url ? `center / cover no-repeat url(${JSON.stringify(p.image_url)})` : gradientFor(p.destination) }}>
                  <span>{p.destination}, {p.country}</span>
                  {p.is_featured && <span className="pkg-flag">★ Featured</span>}
                </div>
                <div className="pkg-body">
                  <h3>{p.title}</h3>
                  <div className="muted small">{p.duration_days} days{p.hotel_stars ? ` · ${"★".repeat(p.hotel_stars)} hotel` : ""}</div>
                  <div className="tag-row">{p.tags.slice(0, 4).map((t) => <span key={t} className="tag">{t}</span>)}</div>
                  <div className="row-between">
                    <div className="pkg-price">{money(p.price_per_person, p.currency)}<span className="muted small"> / person</span></div>
                    <button className="btn btn-sm btn-primary" onClick={(e) => { e.stopPropagation(); askAbout(p); }}>Book</button>
                  </div>
                </div>
              </article>
            ))}
          </div>
        )}
      </main>

      <footer className="sf-footer">
        {company.name} · {company.contact_email ?? ""} · Payments are handled by our team, never by the chat.
      </footer>

      {selected && (
        <Modal title={selected.title} onClose={() => setSelected(null)} wide>
          <div className="pkg-cover big" style={{ background: selected.image_url ? `center / cover no-repeat url(${JSON.stringify(selected.image_url)})` : gradientFor(selected.destination) }}>
            <span>{selected.destination}, {selected.country} · {selected.duration_days} days</span>
          </div>
          <p>{selected.description}</p>
          <div className="grid-2">
            <div>
              <h4>Included</h4>
              <ul className="ticks">{selected.includes.map((i) => <li key={i}>{i}</li>)}</ul>
            </div>
            <div>
              <h4>Not included</h4>
              <ul className="crosses">{selected.excludes.map((i) => <li key={i}>{i}</li>)}</ul>
            </div>
          </div>
          <dl className="details">
            <dt>Hotel</dt><dd>{selected.hotel_name ?? "—"} {selected.hotel_stars ? "★".repeat(selected.hotel_stars) : ""}</dd>
            <dt>Departures</dt><dd>{selected.departure_dates.length ? selected.departure_dates.map(shortDate).join(" · ") : "Flexible, on request"}</dd>
            <dt>Price</dt><dd><strong>{money(selected.price_per_person, selected.currency)}</strong> per adult
              {selected.child_price != null && <> · {money(selected.child_price, selected.currency)} per child</>}</dd>
            {selected.seats_available != null && <><dt>Seats left</dt><dd>{selected.seats_available}</dd></>}
          </dl>
          <div className="modal-actions"><span className="spacer" />
            <button className="btn btn-primary" onClick={() => askAbout(selected)}>Book with {company.ai_agent_name}</button>
          </div>
        </Modal>
      )}

      {chatOpen ? (
        <ChatWidget slug={slug} company={company} prefill={prefill} onPrefillUsed={() => setPrefill(null)} onClose={() => setChatOpen(false)} />
      ) : (
        <button className="chat-fab" onClick={() => setChatOpen(true)}>💬 Chat with {company.ai_agent_name}</button>
      )}
    </div>
  );
}

function ChatWidget({ slug, company, prefill, onPrefillUsed, onClose }: {
  slug: string; company: PublicCompany; prefill: string | null; onPrefillUsed: () => void; onClose: () => void;
}) {
  const storageKey = `travel_chat_${slug}`;
  const [token, setToken] = useState<string | null>(null);
  const [messages, setMessages] = useState<PublicMessage[]>([]);
  const [status, setStatus] = useState("ai");
  const [text, setText] = useState("");
  const [waiting, setWaiting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const bottom = useRef<HTMLDivElement>(null);
  const started = useRef(false);
  const base = `/api/public/companies/${slug}/chats`;

  const merge = useCallback((incoming: PublicMessage[]) => {
    setMessages((prev) => {
      const known = new Set(prev.filter((m) => m.id > 0).map((m) => m.id));
      const kept = prev.filter((m) => m.id > 0);
      return [...kept, ...incoming.filter((m) => !known.has(m.id))].sort((a, b) => a.id - b.id);
    });
  }, []);

  const startNew = useCallback(async () => {
    const res = await post<{ token: string; status: string; messages: PublicMessage[] }>(base, {});
    try { localStorage.setItem(storageKey, res.token); } catch { /* ignore */ }
    setToken(res.token);
    setStatus(res.status);
    setMessages(res.messages);
    return res.token;
  }, [base, storageKey]);

  // Resume the previous chat on this device, or start a new one.
  useEffect(() => {
    if (started.current) return;
    started.current = true;
    let saved: string | null = null;
    try { saved = localStorage.getItem(storageKey); } catch { /* ignore */ }
    if (!saved) { startNew().catch((e) => setError(e.message)); return; }
    get<{ status: string; messages: PublicMessage[] }>(`${base}/${saved}/messages?after_id=0`)
      .then((r) => { setToken(saved); setStatus(r.status); setMessages(r.messages); })
      .catch(() => startNew().catch((e) => setError(e.message)));
  }, [base, storageKey, startNew]);

  // Pick up replies written by employees.
  useEffect(() => {
    if (!token) return;
    const id = window.setInterval(() => {
      if (waiting || document.visibilityState !== "visible") return;
      const last = messages.filter((m) => m.id > 0).slice(-1)[0]?.id ?? 0;
      get<{ status: string; messages: PublicMessage[] }>(`${base}/${token}/messages?after_id=${last}`)
        .then((r) => { setStatus(r.status); if (r.messages.length) merge(r.messages); })
        .catch(() => {});
    }, 5000);
    return () => window.clearInterval(id);
  }, [token, messages, waiting, base, merge]);

  useEffect(() => { bottom.current?.scrollIntoView({ block: "end" }); }, [messages, waiting]);

  const send = useCallback(async (content: string) => {
    if (!content.trim() || !token) return;
    setError(null);
    setWaiting(true);
    setMessages((prev) => [...prev, { id: -Date.now(), sender: "customer", content, created_at: new Date().toISOString() }]);
    try {
      const r = await post<{ status: string; messages: PublicMessage[] }>(`${base}/${token}/messages`, { content });
      setStatus(r.status);
      merge(r.messages);
    } catch (e) {
      setMessages((prev) => prev.filter((m) => m.id > 0));
      setError(e instanceof ApiError && e.status === 429 ? "You're sending messages too fast, please wait a moment." : "Message not sent, please try again.");
      setText(content);
    } finally {
      setWaiting(false);
    }
  }, [token, base, merge]);

  useEffect(() => {
    if (prefill && token && !waiting) {
      onPrefillUsed();
      send(prefill);
    }
  }, [prefill, token, waiting, send, onPrefillUsed]);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const content = text.trim();
    setText("");
    send(content);
  };

  const restart = () => {
    try { localStorage.removeItem(storageKey); } catch { /* ignore */ }
    setMessages([]);
    startNew().catch((e) => setError(e.message));
  };

  return (
    <div className="chat-widget">
      <div className="cw-head">
        <div className="cw-avatar">{company.ai_agent_name.charAt(0)}</div>
        <div>
          <div className="cw-name">{company.ai_agent_name} · {company.name}</div>
          <div className="cw-sub">{status === "human" ? "A travel consultant is with you" : "AI travel consultant · replies instantly"}</div>
        </div>
        <button className="icon-btn light" title="New conversation" onClick={restart}>↻</button>
        <button className="icon-btn light" onClick={onClose} aria-label="Close chat">×</button>
      </div>
      <div className="cw-body">
        {messages.map((m) => (
          <div key={m.id} className={`cw-msg ${m.sender === "customer" ? "me" : "them"}`}>
            {m.sender === "agent" && <div className="cw-who">Travel consultant</div>}
            <div className="cw-bubble"><ChatText text={m.content} /></div>
          </div>
        ))}
        {waiting && status !== "human" && <div className="cw-msg them"><div className="cw-bubble typing"><span /><span /><span /></div></div>}
        <div ref={bottom} />
      </div>
      {error && <div className="cw-error">{error}</div>}
      <form className="cw-input" onSubmit={submit}>
        <input value={text} onChange={(e) => setText(e.target.value)} placeholder="Type your message…" disabled={!token} maxLength={2000} />
        <button className="btn btn-primary" disabled={!text.trim() || waiting || !token}>Send</button>
      </form>
    </div>
  );
}
