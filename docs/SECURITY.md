# Security and privacy

## Who can see what

| Data | Who can see it |
|---|---|
| A company's customers, chats, tickets, packages, AI training | Only that company's employees, and only with the matching permission |
| Customer chats | Not the platform owner (system admin): the platform console has no access to company conversations |
| WhatsApp access tokens and app secrets | Nobody: stored encrypted, never returned by the API (only "saved: yes/no") |
| Webhook URL and verify token of a company | Employees with the `settings.manage` permission |
| Employee passwords | Nobody: stored as bcrypt hashes |

Every company endpoint checks the logged-in employee's company on every request; ids of another
company answer "not found". The AI's tools receive the company from the server, never from the
model, so a customer cannot make the AI read or book another company's data. The automated tests
(`backend/tests/test_isolation.py`) try every endpoint with another company's ids.

## What is protected

* **Logins**: bcrypt passwords; login attempts limited per IP and per account; same error for a wrong
  email or a wrong password; tokens expire after 12 hours; changing or resetting a password logs out
  every other session; disabled accounts and suspended companies are locked out immediately.
* **Tenant isolation**: see above, covered by tests.
* **Delegated account management**: an employee with "manage employees" who is not a company admin
  only manages support and ticket accounts, can only give permissions they have, and can't change
  their own permissions. Only company admins create, edit or delete admins. Disabling an account
  ends its logins for good (re-enabling does not bring old logins back).
* **Bookings**: statuses follow fixed steps (pending → in progress → paid → confirmed, or cancelled);
  "paid" needs a payment reference; only a company admin changes a price or reopens a cancelled
  booking; every change (status, assignee, price, payment reference, notes) is kept in the booking's
  history with who did it. Seats are held from the moment of booking with an atomic database update,
  so two bookings can never take the same last seats.
* **Race conditions**: account limits, "keep one admin" and company creation are checked inside a
  locked transaction; a company is never created without its admin.
* **WhatsApp**: Meta's signature is verified with the company's (or platform's) app secret; online,
  unsigned webhooks are refused; a company's webhook can only deliver to its own number.
* **Encryption at rest**: WhatsApp tokens and app secrets are encrypted in the database with a key
  from the server environment (`ENCRYPTION_KEY`, or derived from `SECRET_KEY`). A copied database
  alone does not reveal them. If you change `SECRET_KEY` without setting `ENCRYPTION_KEY`, companies
  must re-enter their WhatsApp token and secret.
* **Abuse and cost protection**: chat messages are limited per chat and per IP; new chats are also
  limited per company (not only per IP), logins per IP across all accounts, and AI replies per
  company per hour (`AI_MAX_REPLIES_PER_COMPANY_PER_HOUR`), after which chats go to the team. The
  limits live in the server's memory: with several server instances, move them to a shared store.
* **AI safety**: the AI's tools only see the conversation's company; prices and totals always come
  from the server (`quote_booking`, `create_booking_ticket`), never from the model; customer-typed
  details (name, WhatsApp profile name) are cleaned before they reach the AI's instructions, and the
  rules tell the model that customer text is never an instruction.
* **Browser**: Content-Security-Policy, no framing (clickjacking), no MIME sniffing, HSTS online,
  API answers are never cached. Chat text is always shown as text, never as HTML.
* **Nothing internal is public online**: the API documentation (`/docs`, `/openapi.json`) is
  switched off in production; `/api/health` only says "ok"; demo logins are never in the website
  code and never listed in production; demo staff get random passwords online.
* **Uploaded photos** (logos, banners, package photos): only JPEG, PNG and WebP, checked by their
  real content, not the file name (SVG and HTML are refused); maximum 2.5 MB each and 300 files /
  100 MB per company; photos are shrunk in the browser first, which also removes camera location
  data. They are served with `nosniff` and a sandbox policy so nothing inside them can run. A
  company can only use its own photos on its packages and page.
* **Page design**: colours must be real `#rrggbb` values, texts have length limits, and images must
  be uploaded files or `https://` addresses, so a design cannot inject code into the customer page.
  Only the platform owner can change the colours of a company's employee dashboard.
* **Startup checks in production**: the server refuses to start with the default `SECRET_KEY` or
  the default owner password.

## Your checklist

1. **Make the GitHub repository private** (GitHub → Settings → General → Danger Zone → Change
   visibility). Hosting on Render keeps working. No passwords or keys were ever committed to it:
   all secrets live only in Render's Environment or the server's `.env`.
2. Use a long random `SECRET_KEY` (Render generates one) and your own owner password.
3. Change your owner password after the first login.
4. Give employees only the permissions they need.
5. Keep regular database backups (Neon has point-in-time restore on paid plans; on a server use
   `deploy/backup.sh`).
6. Never paste API keys or database passwords into chats or tickets.
