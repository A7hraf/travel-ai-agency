# Connecting WhatsApp

The platform uses the official **WhatsApp Cloud API** from Meta. **Every travel company has its
own WhatsApp channel**: its own number, and (recommended) its own Meta app. A customer who writes to
a company's number talks only to that company's AI agent, and the chat is visible only to that
company's team.

## How a message finds the right company

* **Website**: each company has its own page, `https://YOUR-ADDRESS/c/<company>`. The chat started
  there belongs to that company.
* **WhatsApp**: each company connects its own number. Meta tells the platform which number received
  the message, so the chat goes to the company that owns that number. A number can be connected to
  only one company.
* The AI never mixes companies: for every reply it only receives that company's packages, policies,
  training answers and that one conversation.

## Option A: the company uses its own Meta app (recommended)

1. The company creates (or uses) a Meta app at <https://developers.facebook.com/apps> → **Create
   app** → type **Business** → add the **WhatsApp** product, and adds its phone number under
   **WhatsApp → API Setup** (Meta also gives a free test number).
2. It copies, from Meta:
   * the **Phone number ID** (WhatsApp → API Setup),
   * a permanent **access token** (Business settings → Users → System users → Generate token with
     `whatsapp_business_messaging` and `whatsapp_business_management`),
   * the **App secret** (App settings → Basic).
3. The company admin opens **AI & WhatsApp** in the dashboard, fills in those three values and the
   public number, and saves. Tokens and secrets are stored encrypted and are never shown again.
4. The same page shows the company's own **Callback URL** and **Verify token**. In Meta → WhatsApp
   → Configuration → Webhook: paste both, click **Verify and save**, and subscribe to **messages**.
5. Send a WhatsApp message to the number: the AI answers, and the chat appears in
   **Conversations** with a 🟢 WhatsApp label.

The company's webhook only accepts messages signed with that company's app secret, and only for
that company's own number.

## Option B: one shared Meta app for all companies (platform owner)

Useful if you (the platform owner) onboard the companies' numbers into your own Meta app.

1. Set `WHATSAPP_APP_SECRET` (your app's secret) and `WHATSAPP_VERIFY_TOKEN` (any random text) in
   the server environment (Render → Environment, or `.env`).
2. In your Meta app's webhook: Callback URL `https://YOUR-ADDRESS/api/webhooks/whatsapp`, the
   verify token above, subscribe to **messages**.
3. Each company still enters its own Phone number ID (and access token) in **AI & WhatsApp**.

Online (production), the shared webhook is switched off until `WHATSAPP_APP_SECRET` is set, so
nobody can post fake messages.

## Details

* Meta's signature (`X-Hub-Signature-256`) is checked on every webhook call. The request is answered
  immediately and the AI reply is sent in the background.
* The customer's WhatsApp number becomes their phone number, so the AI does not ask for it again.
* Duplicate deliveries from Meta are ignored. Incoming messages are marked as read. Delivery receipts
  (sent / delivered / read / failed) are shown under each reply in the dashboard.
* Text, buttons and list replies are understood; for images, voice notes etc. the AI asks the
  customer to type their request.
* When an employee replies from the dashboard, the message goes out on WhatsApp.

## The 24-hour rule

WhatsApp only allows free-form messages within 24 hours of the customer's last message. After that,
businesses must send an approved **template** message. If an employee replies too late, the
dashboard shows that WhatsApp did not deliver it.
