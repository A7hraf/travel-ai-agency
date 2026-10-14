# Put Ghanjah online for free (Render + Neon + Groq)

Total cost: **$0**. Time: about 20 minutes. You only need a browser.

| Part | Free service | What it does |
|---|---|---|
| Website + API | [Render](https://render.com) | Runs the app from your GitHub repo and gives it an `https://….onrender.com` address |
| Database | [Neon](https://neon.tech) | Free PostgreSQL that does not expire |
| AI brain | [Groq](https://console.groq.com) | Runs the open-source gpt-oss model (Apache 2.0) |

After this setup, **every change pushed to the `main` branch on GitHub goes live automatically**
(Render rebuilds the site by itself).

Free plans change often; check each provider's pricing page if something below looks different.

## Limits of the free plans (good for testing and first customers)

* **Render free**: the site **sleeps after 15 minutes without visitors**. The next visitor waits
  about a minute while it wakes up. A WhatsApp message that arrives while it sleeps is answered once
  it is awake (Meta retries). A paid Render plan keeps it always on.
* **Groq free**: limited requests and tokens per minute and per day (check your limits in the Groq
  console). One customer message uses 2–3 AI requests, so this is enough for testing and a few
  dozen customer messages a day. When the limit is reached, customers get a polite "a consultant
  will reply" message and the chat goes to your team. For more, switch to Groq's paid
  pay-as-you-go plan (same settings, no code change).
* **Models get retired.** Groq retired Llama 3.3 70B in August 2026. The app now uses
  `openai/gpt-oss-120b` with `openai/gpt-oss-20b` as automatic backup, and the **Test AI** button
  (platform console and "AI & WhatsApp") shows the exact error if a model stops working.
* **Neon free**: about 0.5–1 GB of data, which is plenty for thousands of chats and bookings.

## Step 1: Database (Neon)

1. Go to <https://neon.tech> and sign up (you can use "Continue with GitHub").
2. Create a project: any name (e.g. `travel-ai`), Postgres version: default,
   region: **AWS Europe Central 1 (Frankfurt)**.
3. On the project dashboard click **Connect**, and copy the **connection string**. It looks like
   `postgresql://neondb_owner:abc123@ep-cool-name-123456.eu-central-1.aws.neon.tech/neondb?sslmode=require`
4. Keep it for step 3. Treat it like a password.

## Step 2: AI key (Groq)

1. Go to <https://console.groq.com> and sign in.
2. Open **API Keys** → **Create API Key**, give it a name, and copy the key (starts with `gsk_`).
   You only see it once.

## Step 3: Website (Render)

1. Go to <https://render.com> and click **Get Started** → **Sign up with GitHub**.
2. When GitHub asks which repositories Render may access, choose **Only select repositories** →
   `travel-ai-agency`.
3. In Render click **New +** → **Blueprint**, pick the `travel-ai-agency` repository, and click
   **Connect**. Render reads the [`render.yaml`](../render.yaml) file from the repo.
4. Render asks for 4 values:

   | Name | What to paste |
   |---|---|
   | `DATABASE_URL` | the Neon connection string from step 1 |
   | `SYSTEM_ADMIN_EMAIL` | the email you will log in with (you, the platform owner) |
   | `SYSTEM_ADMIN_PASSWORD` | a strong password, at least 8 characters |
   | `LLM_API_KEY` | the Groq key from step 2 |

5. Click **Apply** / **Deploy Blueprint**. The first build takes 5–10 minutes.
6. When it says **Live**, open the address at the top of the service page, e.g.
   `https://ghanjah.onrender.com` (the service name in `render.yaml` is `ghanjah`; if another
   Render user already has that name, Render adds a few random letters).

## Step 4: First login

1. Log in with your `SYSTEM_ADMIN_EMAIL` and `SYSTEM_ADMIN_PASSWORD`.
2. On the **Companies** page click **Test AI**. It must say **✓ Working**. If not, it shows the
   exact problem (wrong key, retired model…).
3. The demo agency **Sunrise Travel** (Muscat, prices in Omani rials) is there to try things:
   * Customer page with the AI chat: `https://YOUR-ADDRESS/c/sunrise-travel` (English / العربية)
   * Online, its staff logins get random passwords. To use them: **Companies → Sunrise Travel →
     Manage → Edit** an account and set a new password.
4. Create your first real company: **Companies → + New company** (name, account limit, and the
   company admin's login). The company admin then adds packages, AI training, AI settings and
   employees.

## Step 5: Before real customers

1. Make your GitHub repository **private**: GitHub → your repo → **Settings → General → Danger
   Zone → Change visibility → Private**. Render keeps working.
2. If you don't need the demo: in Render → **Environment** set `SEED_DEMO_DATA` to `false`, then
   **Companies → Sunrise Travel → Delete company permanently**.
3. Change your password in **My account** (this logs out every other device).

## Step 6: WhatsApp (optional)

Follow [WHATSAPP_SETUP.md](WHATSAPP_SETUP.md) with:

* Webhook URL: `https://YOUR-ADDRESS/api/webhooks/whatsapp`
* Easiest: each company connects its own Meta app in **AI & WhatsApp**, which shows the company's
  own webhook URL and verify token.
* Shared platform app (optional): webhook `https://YOUR-ADDRESS/api/webhooks/whatsapp`, verify
  token in Render → **Environment** → `WHATSAPP_VERIFY_TOKEN`, and add `WHATSAPP_APP_SECRET`.

## Moving an existing service to the Ghanjah address

Render can't rename the address of a service that already exists (the old one was
`travel-ai-agency.onrender.com`). Since `render.yaml` now names the service `ghanjah`, Render creates
a **new** service with the address `https://ghanjah.onrender.com`. Your data stays in Neon, so
nothing is lost. The old service keeps working until you delete it.

1. Open the old service **travel-ai-agency** → **Environment** and keep this tab open. You will copy
   `DATABASE_URL`, `SYSTEM_ADMIN_EMAIL`, `SYSTEM_ADMIN_PASSWORD`, `LLM_API_KEY`, **`SECRET_KEY`** and
   `WHATSAPP_VERIFY_TOKEN` (and `ENCRYPTION_KEY` / `WHATSAPP_APP_SECRET` if you added them).
2. In Render open **Blueprints** → your blueprint. It shows the new service `ghanjah` and asks for
   the 4 values (`DATABASE_URL`, `SYSTEM_ADMIN_EMAIL`, `SYSTEM_ADMIN_PASSWORD`, `LLM_API_KEY`):
   paste the same ones as the old service and click **Apply**.
3. Open the new service **ghanjah** → **Environment** and replace the generated `SECRET_KEY` and
   `WHATSAPP_VERIFY_TOKEN` with the **old service's values**, then **Save, rebuild and deploy**.
   This is important: the secret key unlocks the saved WhatsApp tokens and keeps everyone logged in.
4. Open `https://ghanjah.onrender.com`, log in, and press **Test AI**.
5. WhatsApp: in each Meta app change the webhook **Callback URL** to the new address (the path
   after the domain stays the same; it is shown in **AI & WhatsApp** settings).
6. When everything works, delete the old service (**travel-ai-agency → Settings → Delete Web
   Service**) so the free hours are not shared between two services.

Optional: rename the GitHub repository to `ghanjah` (GitHub → Settings → Repository name). GitHub
redirects the old name and Render follows the rename.

## Your own domain (optional)

Buy a domain (about $10–15 per year), then in Render → your service → **Settings → Custom
Domains** add e.g. `ghanjah.om` or `www.ghanjah.com` and create the DNS record Render shows you. HTTPS is
automatic.

## Changing settings later

Render → your service → **Environment**. Useful ones:

| Variable | Meaning |
|---|---|
| `LLM_MODEL` | AI model at Groq, e.g. `openai/gpt-oss-120b` (best) or `openai/gpt-oss-20b` (faster) |
| `LLM_FALLBACK_MODELS` | backup models tried automatically if the main one is retired |
| `LLM_BASE_URL`, `LLM_API_KEY` | use another OpenAI-compatible AI provider |
| `SEED_DEMO_DATA` | `true` / `false` |

## When you outgrow the free plan

Move to a server with [DEPLOY_SERVER.md](DEPLOY_SERVER.md): always on, your own AI on the same
machine if you want, one command to install. Your data can be moved with `pg_dump` from Neon.
