# Connecting WhatsApp

The platform uses the official **WhatsApp Cloud API** from Meta. You (the platform owner) create
one Meta app and one webhook; each travel company connects its own WhatsApp Business phone number.

## 1. Platform owner: create the Meta app (once)

1. Go to <https://developers.facebook.com/apps> → **Create app** → type **Business**.
2. Add the **WhatsApp** product.
3. **App settings → Basic**: copy the **App secret** into `.env` as `WHATSAPP_APP_SECRET`.
4. Choose any random string as `WHATSAPP_VERIFY_TOKEN` in `.env` and restart the backend.
5. **WhatsApp → Configuration → Webhook**:
   * Callback URL: `https://YOUR-DOMAIN/api/webhooks/whatsapp` (must be public HTTPS)
   * Verify token: the value of `WHATSAPP_VERIFY_TOKEN`
   * Click **Verify and save**, then **subscribe to the `messages` field**.

For local testing, expose your machine with a tunnel (e.g. `cloudflared tunnel --url http://localhost:8080`
or `ngrok http 8080`) and use that HTTPS URL.

## 2. Each travel company: connect its number

1. In Meta **WhatsApp → API Setup**, add and verify the company's phone number (Meta also gives a
   free test number for trying it out).
2. Copy the **Phone number ID** (not the phone number itself).
3. Create a permanent access token: **Business settings → Users → System users** → add a system
   user → **Generate token** for your app with `whatsapp_business_messaging` and
   `whatsapp_business_management` permissions. (The temporary token on the API Setup page expires
   after 24 hours.)
4. In the app, log in as the company admin → **AI & WhatsApp** → fill in:
   * Phone number ID
   * Public WhatsApp number (shown as a "WhatsApp us" button on the customer page)
   * Access token
5. Send a WhatsApp message to the number: the AI answers, and the chat appears in
   **Conversations** with a 🟢 WhatsApp label.

A phone number ID can only be connected to one company. Messages for a suspended company are
ignored.

## How it works

* Meta calls `POST /api/webhooks/whatsapp`. The signature (`X-Hub-Signature-256`) is checked with
  the app secret, the request is answered immediately, and the AI reply is generated in the
  background, then sent with the Graph API.
* The receiving `phone_number_id` decides which company the message belongs to.
* The customer's WhatsApp number becomes their phone number, so the AI does not ask for it again.
* Duplicate deliveries from Meta are ignored. Incoming messages are marked as read. Delivery
  receipts (sent / delivered / read / failed) are shown under each reply in the dashboard.
* Text, buttons and list replies are understood; for images, voice notes etc. the AI asks the
  customer to type their request.
* When an employee replies from the dashboard, the message goes out on WhatsApp.

## The 24-hour rule

WhatsApp only allows free-form messages within 24 hours of the customer's last message. After
that, businesses must send an approved **template** message. If an employee replies too late, the
dashboard shows that WhatsApp did not deliver it.
