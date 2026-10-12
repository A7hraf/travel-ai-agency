#!/usr/bin/env bash
# One-command installer for an Ubuntu / Debian server.
#
#   cd travel-ai-agency
#   sudo bash deploy/install.sh
#
# It installs Docker if needed, asks a few questions, writes .env (keeping the
# secrets of a previous install), and starts the system with automatic HTTPS.
# Safe to run again later, e.g. to switch to your own domain or another AI.
#
# Answers can also be given as environment variables (NONINTERACTIVE=1 uses the
# defaults for anything not given): DOMAIN, OWNER_EMAIL, OWNER_PASSWORD,
# AI_CHOICE (1 Groq, 2 local Ollama, 3 demo), GROQ_API_KEY, DEMO_DATA (y/n).
set -euo pipefail

cd "$(dirname "$0")/.."
ENV_FILE=.env

info() { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m!!  %s\033[0m\n' "$*"; }
die() { printf '\033[1;31mxx  %s\033[0m\n' "$*" >&2; exit 1; }

# ask VAR "question" "default": keeps a value already given in the environment.
ask() {
  local var=$1 question=$2 default=${3:-} answer=""
  if [ -n "${!var:-}" ]; then return; fi
  if [ "${NONINTERACTIVE:-0}" != 1 ]; then
    read -r -p "$question${default:+ [$default]}: " answer </dev/tty || true
  fi
  printf -v "$var" '%s' "${answer:-$default}"
}

# Value of KEY in the existing .env (empty if missing).
current() { [ -f "$ENV_FILE" ] && grep -E "^$1=" "$ENV_FILE" | tail -n 1 | cut -d= -f2- || true; }

random_hex() { openssl rand -hex "${1:-24}" 2>/dev/null || python3 -c "import secrets; print(secrets.token_hex(${1:-24}))"; }

# --- 1. Requirements ------------------------------------------------------------
[ "$(id -u)" = 0 ] || die "Please run as root: sudo bash deploy/install.sh"

if ! command -v docker >/dev/null 2>&1; then
  info "Installing Docker"
  curl -fsSL https://get.docker.com | sh
fi
docker compose version >/dev/null 2>&1 || die "Docker Compose plugin is missing (apt-get install docker-compose-plugin)"

mem_mb=$(awk '/MemTotal/ {print int($2/1024)}' /proc/meminfo)
if [ "$mem_mb" -lt 3500 ] && ! swapon --show 2>/dev/null | grep -q .; then
  info "Small server (${mem_mb} MB RAM): adding 2 GB of swap"
  { fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile >/dev/null && swapon /swapfile \
    && echo '/swapfile none swap sw 0 0' >> /etc/fstab; } || warn "Could not add swap; continuing"
fi

# --- 2. Questions -----------------------------------------------------------------
info "A few questions (press Enter to accept the [default])"

old_domain=$(current DOMAIN)
if [ -z "${DOMAIN:-}" ] && { [ -z "$old_domain" ] || [ "$old_domain" = localhost ]; }; then
  ip=$(curl -fsS -4 --max-time 10 https://api.ipify.org 2>/dev/null || hostname -I | awk '{print $1}')
  suggested="${ip//./-}.sslip.io"
  echo "No domain yet? Use the free address $suggested (it points to this server)."
  echo "You can switch to your own domain later by running this installer again."
else
  suggested=$old_domain
fi
ask DOMAIN "Domain name for the website" "$suggested"
DOMAIN=${DOMAIN#http://}; DOMAIN=${DOMAIN#https://}; DOMAIN=${DOMAIN%%/*}
[ -n "$DOMAIN" ] || die "A domain is required"

ask OWNER_EMAIL "Your login email (platform owner)" "$(current SYSTEM_ADMIN_EMAIL || true)"
OWNER_EMAIL=${OWNER_EMAIL:-owner@example.com}
old_password=$(current SYSTEM_ADMIN_PASSWORD)
if [ -n "$old_password" ] && [ "$old_password" != "ChangeMe123!" ]; then
  OWNER_PASSWORD=${OWNER_PASSWORD:-$old_password}
fi
ask OWNER_PASSWORD "Your login password (empty = generate one)" ""
OWNER_PASSWORD=${OWNER_PASSWORD:-$(random_hex 6)}

echo
echo "Which AI brain?"
echo "  1) Groq cloud: open-source gpt-oss, fast, has a free tier   (recommended)"
echo "  2) Ollama on this server: fully private, needs 16 GB RAM, slow without a GPU"
echo "  3) Demo mode: no real AI, to try the screens"
old_choice=1
case "$(current LLM_PROVIDER)/$(current LLM_BASE_URL)" in
  mock/*) old_choice=3 ;;
  */http://ollama*) old_choice=2 ;;
esac
ask AI_CHOICE "Choose 1, 2 or 3" "$old_choice"

profiles=https
llm_provider=openai_compatible
llm_model=$(current LLM_MODEL)
llm_key=$(current LLM_API_KEY)
case "$AI_CHOICE" in
  1)
    [ "$(current LLM_BASE_URL)" = "https://api.groq.com/openai/v1" ] || llm_key=""
    if [ -n "$llm_key" ]; then
      ask GROQ_API_KEY "Groq API key (press Enter to keep the saved key)" ""
      GROQ_API_KEY=${GROQ_API_KEY:-$llm_key}
    else
      ask GROQ_API_KEY "Groq API key (from https://console.groq.com/keys)" ""
    fi
    if [ -z "$GROQ_API_KEY" ]; then
      warn "No Groq key given: starting in demo mode. Run the installer again when you have a key."
      llm_provider=mock; llm_url=https://api.groq.com/openai/v1; llm_key=""; llm_model=openai/gpt-oss-120b
    else
      llm_url=https://api.groq.com/openai/v1; llm_key=$GROQ_API_KEY
      case "$llm_model" in ""|travel-agent|llama-3.3-70b-versatile|llama-3.1-8b-instant) llm_model=openai/gpt-oss-120b ;; esac
    fi
    ;;
  2)
    profiles=https,local-ai
    llm_url=http://ollama:11434/v1; llm_key=ollama; llm_model=travel-agent
    [ "$mem_mb" -ge 15000 ] || warn "This server has ${mem_mb} MB RAM; 16 GB is recommended for the local AI."
    ;;
  *)
    llm_provider=mock; llm_url=http://ollama:11434/v1; llm_key=""; llm_model=travel-agent
    ;;
esac

old_demo=$(current SEED_DEMO_DATA)
ask DEMO_DATA "Add the demo travel company 'Sunrise Travel'? (y/n)" "$([ "$old_demo" = true ] && echo y || echo n)"
case "$DEMO_DATA" in y|Y|yes|YES) seed=true ;; *) seed=false ;; esac

# --- 3. Write .env (secrets of a previous install are kept) ---------------------
secret_key=$(current SECRET_KEY)
[ ${#secret_key} -ge 32 ] && [ "$secret_key" != replace-with-a-long-random-string ] || secret_key=$(random_hex 32)
db_password=$(current POSTGRES_PASSWORD)
[ -n "$db_password" ] && [ "$db_password" != change-this-db-password ] || db_password=$(random_hex 16)
verify_token=$(current WHATSAPP_VERIFY_TOKEN)
[ -n "$verify_token" ] && [ "$verify_token" != choose-a-random-verify-token ] || verify_token=$(random_hex 12)

[ -f "$ENV_FILE" ] && cp "$ENV_FILE" "$ENV_FILE.backup"
umask 077
cat > "$ENV_FILE" <<EOF
# Written by deploy/install.sh on $(date -u +%Y-%m-%d). Run the installer again to change answers.
COMPOSE_PROFILES=$profiles
DOMAIN=$DOMAIN

ENVIRONMENT=production
SECRET_KEY=$secret_key
SYSTEM_ADMIN_EMAIL=$OWNER_EMAIL
SYSTEM_ADMIN_PASSWORD=$OWNER_PASSWORD
SYSTEM_ADMIN_NAME=$(current SYSTEM_ADMIN_NAME | grep . || echo "Platform Owner")
SEED_DEMO_DATA=$seed
WEB_PORT=8080
WEB_BIND=127.0.0.1
CORS_ORIGINS=https://$DOMAIN

POSTGRES_USER=travel
POSTGRES_PASSWORD=$db_password
POSTGRES_DB=travel_ai

LLM_PROVIDER=$llm_provider
LLM_BASE_URL=$llm_url
LLM_API_KEY=$llm_key
LLM_MODEL=$llm_model
LLM_FALLBACK_MODELS=$([ "$llm_url" = "https://api.groq.com/openai/v1" ] && echo "openai/gpt-oss-20b")
LLM_REASONING_EFFORT=$([ "$llm_url" = "https://api.groq.com/openai/v1" ] && echo "low")
LLM_TEMPERATURE=0.3
BASE_MODEL=$(current BASE_MODEL | grep . || echo "qwen2.5:7b")

WHATSAPP_VERIFY_TOKEN=$verify_token
WHATSAPP_APP_SECRET=$(current WHATSAPP_APP_SECRET)
WHATSAPP_API_VERSION=$(current WHATSAPP_API_VERSION | grep . || echo "v21.0")
WHATSAPP_DEFAULT_ACCESS_TOKEN=$(current WHATSAPP_DEFAULT_ACCESS_TOKEN)
EOF
umask 022

# --- 4. Firewall and start ----------------------------------------------------------
if command -v ufw >/dev/null 2>&1 && ufw status 2>/dev/null | grep -q "Status: active"; then
  info "Opening ports 80 and 443 in the firewall"
  ufw allow 80/tcp >/dev/null; ufw allow 443/tcp >/dev/null; ufw allow 443/udp >/dev/null
fi

info "Building and starting (the first time takes a few minutes)"
docker compose up -d --build --remove-orphans

info "Waiting for the system to answer"
ok=0
for _ in $(seq 1 90); do
  if curl -fsS --max-time 5 http://127.0.0.1:8080/api/health >/dev/null 2>&1; then ok=1; break; fi
  sleep 2
done
[ "$ok" = 1 ] || die "The system did not start. See: docker compose logs backend"

https_ok=0
for _ in $(seq 1 30); do
  if curl -fsS --max-time 10 "https://$DOMAIN/api/health" >/dev/null 2>&1; then https_ok=1; break; fi
  sleep 4
done

# --- 5. Summary ----------------------------------------------------------------
echo
printf '\033[1;32m%s\033[0m\n' "Travel AI Agency is running."
echo
echo "  Website (staff login):  https://$DOMAIN"
echo "  Your login:             $OWNER_EMAIL"
echo "  Your password:          $OWNER_PASSWORD"
[ "$seed" = true ] && echo "  Demo customer page:     https://$DOMAIN/c/sunrise-travel"
echo
echo "  WhatsApp webhook URL:   https://$DOMAIN/api/webhooks/whatsapp"
echo "  WhatsApp verify token:  $verify_token"
echo
if [ "$https_ok" != 1 ]; then
  warn "HTTPS is not answering yet. If you just pointed your domain to this server, wait a few"
  warn "minutes and open the address again. Check: docker compose logs caddy"
fi
[ "$AI_CHOICE" = 2 ] && echo "  The AI model is downloading (several GB). Watch: docker compose logs -f ollama-setup"
[ "$llm_provider" = mock ] && warn "AI is in demo mode. Run the installer again with a Groq key for the real AI."
echo "  Your login password is only used the first time; change it later in 'My account'."
echo "  Settings are in $(pwd)/.env"
