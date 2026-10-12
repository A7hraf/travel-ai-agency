# Put it online on your own server (one command)

Always on, no sleeping, room to grow, and optionally the AI running on the same machine.

## What you need

1. **A server (VPS)** with **Ubuntu 22.04 or 24.04**, from any provider (DigitalOcean, Hetzner,
   Vultr, Contabo, OVH, AWS Lightsail, Oracle Cloud…):
   * AI by Groq (recommended to start): **2 CPU, 4 GB RAM**.
   * AI on the server itself (Ollama): **8 CPU, 16 GB RAM** or a GPU server. Without a GPU the
     replies are slow (30 s to 2 min).
   * Free option: Oracle Cloud "Always Free" ARM servers are enough for the Groq setup, but sign-up
     needs a card and free capacity is often unavailable in popular regions.
2. **A domain** (optional to start). Without one, the installer uses a free address like
   `203-0-113-5.sslip.io` that points to your server. With a domain, create a DNS **A record**
   (e.g. `travel.mytravel.com`) pointing to the server's IP address *before* running the installer.
3. A **Groq API key** (free): <https://console.groq.com> → **API Keys**.

## Install

Connect to the server (Windows: open PowerShell; Mac: open Terminal):

```bash
ssh root@YOUR_SERVER_IP
```

Then:

```bash
git clone https://github.com/A7hraf/travel-ai-agency.git
cd travel-ai-agency
sudo bash deploy/install.sh
```

If the repository is private, `git clone` asks for your GitHub username and a **personal access
token** as the password (GitHub → Settings → Developer settings → Personal access tokens →
Fine-grained, read-only access to this repository).

The installer:

1. installs Docker if needed (and adds swap on small servers),
2. asks: domain, your login email and password, which AI (Groq / local Ollama / demo), demo data,
3. writes `.env` with generated secrets (kept if you run it again),
4. starts everything with **automatic HTTPS** (Caddy + Let's Encrypt),
5. prints your website address, login, and WhatsApp webhook details.

Run it again at any time to change answers, e.g. when you buy a domain or get a Groq key.

## Daily operations

| Task | Command (in the `travel-ai-agency` folder) |
|---|---|
| Get the latest version from GitHub | `sudo bash deploy/update.sh` |
| Back up the database | `sudo bash deploy/backup.sh` (files in `backups/`) |
| Automatic daily backup | `sudo crontab -e`, add: `0 3 * * * cd /root/travel-ai-agency && bash deploy/backup.sh` |
| See what is running | `docker compose ps` |
| Logs | `docker compose logs -f backend` (or `caddy`, `ollama-setup`) |
| Restart | `docker compose restart` |
| Stop | `docker compose down` (data is kept) |

Copy the backups somewhere else from time to time (e.g. download them with `scp`).

## Troubleshooting

* **HTTPS does not work**: the domain must point to the server (check the A record), and ports 80
  and 443 must be open in the provider's firewall. Then `docker compose logs caddy`.
* **"Wrong email or password" for the owner**: the owner account is created on the very first
  start only. Changing `SYSTEM_ADMIN_PASSWORD` later does not change it; use **My account**.
* **AI answers "technical problem"**: check the key and model in `.env` (`LLM_API_KEY`,
  `LLM_MODEL`), then `docker compose logs backend`.
