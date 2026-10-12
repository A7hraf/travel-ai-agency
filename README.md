# Travel AI Agency

A multi-company (SaaS) platform where an **open-source AI travel consultant** sells a travel
agency's packages on the **website and WhatsApp**, takes the booking all the way to the payment
step, and then **hands the ticket to the agency's employees**, who collect the payment.

```
Customer (web chat / WhatsApp)
        │
        ▼
 ┌─────────────────────┐   tools (scoped to ONE company)   ┌──────────────────────┐
 │  AI brain           │ ───────────────────────────────▶  │ search_packages       │
 │  Ollama + Qwen 2.5  │                                    │ get_package_details   │
 │  "travel-agent"     │ ◀───────────────────────────────  │ create_booking_ticket │
 └─────────────────────┘                                    │ request_human_agent   │
        │  booking confirmed by the customer                └──────────────────────┘
        ▼
 Ticket "waiting for payment"  ──▶  company employees (dashboard)  ──▶  paid / confirmed
```

## What's inside

| Who | What they can do |
|---|---|
| **Customer** | Browse the agency's offers page (`/c/<company>`, English / العربية, prices in Omani rials with the official rial sign), chat with the AI on the website or on WhatsApp, get recommendations, book. The AI never takes payments. |
| **AI agent** | Understands the trip (destination, dates, travelers, budget), searches the catalog, answers questions from the package details and the company's policies, collects traveler details, confirms the total, creates the booking ticket and hands over to a human for payment. Replies in the customer's language (Arabic, English, French…). Hands over to a human when asked, on complaints, or when stuck. |
| **Company admin** | Creates, edits, disables and deletes employee accounts; picks a role and ticks individual permissions per employee; manages packages, **AI training** (questions & approved answers), the AI persona and knowledge, and the company's own WhatsApp channel. |
| **Support** | Watches AI conversations live, takes over any chat, replies (on web or WhatsApp), hands the chat back to the AI. |
| **Ticket employee** | Works the booking tickets: takes them, records the payment, confirms or cancels (seats are adjusted automatically). |
| **System admin (you)** | Creates travel companies, sets **how many accounts each company may create**, suspends / re-activates / deletes companies, manages any company's accounts. |

Every company has its own accounts, packages, customers, conversations, tickets, AI persona,
AI training and WhatsApp channel, all served by the **same AI brain**. A customer reaches a company
through that company's own link (`/c/<company>`) or its own WhatsApp number, so every chat belongs
to exactly one company. Data is isolated per company on every request, and the AI only ever sees the
company the conversation belongs to. See [docs/SECURITY.md](docs/SECURITY.md).

### Permissions

Roles pre-fill permissions; the company admin can then add or remove any of them per employee.

| Permission | Company admin | Support | Ticket employee |
|---|:-:|:-:|:-:|
| `packages.view` – view packages | ✓ | ✓ | ✓ |
| `packages.manage` – create/edit/delete packages | ✓ | | |
| `conversations.view` – see customer chats | ✓ | ✓ | ✓ |
| `conversations.reply` – reply, take over from the AI | ✓ | ✓ | ✓ |
| `tickets.view` – see booking tickets | ✓ | ✓ | ✓ |
| `tickets.manage` – update status, payment, notes | ✓ | | ✓ |
| `tickets.assign` – assign tickets to others | ✓ | | |
| `users.manage` – manage employee accounts | ✓ | | |
| `settings.manage` – AI persona, knowledge, WhatsApp | ✓ | | |
| `reports.view` – dashboard | ✓ | ✓ | |

Company admins always have every permission. A company can't lock itself out: the last active
admin can't be disabled, demoted or deleted.

## Put it online

| Guide | Cost | Best for |
|---|---|---|
| **[Free: Render + Neon + Groq](docs/DEPLOY_FREE.md)** | $0 | Trying it online and first customers. Browser only, no server. Every push to `main` goes live automatically. Sleeps when idle. |
| **[Your own server, one command](docs/DEPLOY_SERVER.md)** | from a few $ / month | Always on, automatic HTTPS, optional private AI on the same machine. `sudo bash deploy/install.sh` |

## Quick start on your computer (Docker)

Requirements: Docker with Compose. For the AI: 8 GB RAM minimum (16 GB recommended); an NVIDIA
GPU makes replies much faster (see `docker-compose.yml`).

```bash
cp .env.example .env          # edit SECRET_KEY, passwords, WhatsApp settings
docker compose up -d --build
docker compose logs -f ollama-setup   # first run downloads the model (~4.7 GB)
```

Open **http://localhost:8080**.

With `SEED_DEMO_DATA=true` you get a demo agency in Muscat, **Sunrise Travel**, with 10 packages in
Omani rials. On your computer (`ENVIRONMENT=development`) these logins are shown on the login page;
online (production) the demo staff get random passwords:

| Login | Password | Role |
|---|---|---|
| `owner@example.com` | `ChangeMe123!` | System admin (from `.env`) |
| `admin@sunrise-travel.example` | `Admin123!` | Company admin |
| `support@sunrise-travel.example` | `Support123!` | Support |
| `tickets@sunrise-travel.example` | `Tickets123!` | Ticket employee |

Customer page: **http://localhost:8080/c/sunrise-travel**

> Going online? Use one of the guides in [Put it online](#put-it-online): they set the secrets,
> HTTPS (required by WhatsApp) and turn off the demo data for you.

### No GPU? No problem

* Smaller model: set `BASE_MODEL=qwen2.5:3b` in `.env`.
* Or use the same open-source models hosted by an OpenAI-compatible provider (Groq, OpenRouter,
  Together…): set `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`, and `COMPOSE_PROFILES=` (empty)
  in `.env` so Ollama is not started.
* Or `LLM_PROVIDER=mock` to click through the whole app with a simple rule-based stand-in.

## The AI brain

See [docs/AI_BRAIN.md](docs/AI_BRAIN.md). In short:

1. **Open-source model**: Qwen 2.5 7B Instruct (Apache 2.0) served by Ollama. Any model with
   tool calling works (Llama 3.1, Qwen 3, Mistral…), on any OpenAI-compatible server (Ollama,
   vLLM, llama.cpp, LocalAI).
2. **Customised for travel**: [`ai/Modelfile`](ai/Modelfile) builds the `travel-agent` model
   (long context, low temperature, travel persona). At runtime a travel-sales system prompt
   ([`backend/app/ai/prompts.py`](backend/app/ai/prompts.py)) adds the company's name, agent
   name, policies and instructions.
3. **Grounded in your catalog**: the AI only offers what its tools return. Prices are computed by
   the server, never by the model, and the AI is never allowed to take payments.
4. **Safe failure**: if the model is down or confused, the customer gets a polite reply and the
   chat is handed to a human.

## WhatsApp

See [docs/WHATSAPP_SETUP.md](docs/WHATSAPP_SETUP.md). Each company connects its own WhatsApp
Business number (Meta WhatsApp Cloud API) in **AI & WhatsApp** settings; one webhook URL serves all
companies (`https://your-domain/api/webhooks/whatsapp`). Messages are routed to the right company
by the receiving phone number.

## Project layout

```
backend/                 FastAPI + SQLAlchemy (PostgreSQL / SQLite)
  app/ai/                the agent: LLM client, travel prompts, tools, agent loop
  app/routers/           REST API (auth, system admin, users, packages, conversations,
                         tickets, company settings, public storefront/chat, WhatsApp webhook)
  app/services/          conversation handling, WhatsApp Cloud API, account rules
  tests/                 pytest suite (accounts, AI agent, WhatsApp, tickets)
frontend/                React + TypeScript (Vite): staff dashboard, system console, storefront (EN/AR)
ai/                      Ollama Modelfile and model setup script
docs/                    AI brain, WhatsApp, security and deployment guides
deploy/                  server installer (HTTPS with Caddy), update and backup scripts
docker-compose.yml       PostgreSQL + API + web, optional Ollama and HTTPS (profiles)
Dockerfile, render.yaml  all-in-one image and Render blueprint for free hosting
```

## Development

```bash
# backend (Python 3.12+)
cd backend
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
LLM_PROVIDER=mock uvicorn app.main:app --reload     # SQLite by default
pytest

# frontend (Node 20+)
cd frontend
npm install
npm run dev        # http://localhost:5173, proxies /api to :8000
```

API docs (Swagger): http://localhost:8000/docs (development only; switched off in production)

## Configuration

All settings are environment variables; see [`.env.example`](.env.example) and
[`backend/app/config.py`](backend/app/config.py).

## Notes and limits of this first version

* Live updates in the dashboard use polling (every few seconds).
* Rate limits and the "one AI reply at a time per conversation" lock are in memory: run one backend
  process per container and scale with more containers behind a load balancer + a shared limiter
  if you grow large.
* Database tables are created on start-up; add Alembic migrations before changing the schema in
  production.
* WhatsApp only allows free-form messages within 24 hours of the customer's last message; after
  that an approved template is needed (the dashboard shows the delivery failure).
* WhatsApp access tokens are stored in the database and never returned by the API; encrypt the
  database volume / use a secrets manager in production.

## Ideas for next steps

Online payment links (Stripe / local gateways) on the ticket, email/WhatsApp notifications to
employees on handover, WhatsApp template messages, voice notes (speech-to-text), images on
packages, analytics per channel, per-company plans and billing for the system admin.
