# The AI brain

One open-source model serves every travel company. What makes it a travel agent is the layer
around it: a travel-sales prompt, tools bound to one company's catalog, and the server-side rules.

## 1. The model

| | |
|---|---|
| Hosted (Render guide) | **gpt-oss 120B** (`openai/gpt-oss-120b`, Apache 2.0) on Groq, backup `openai/gpt-oss-20b`, reasoning effort `low` |
| Self-hosted (server guide) | **Qwen 2.5 7B Instruct** (`qwen2.5:7b`, Apache 2.0) in [Ollama](https://ollama.com) |
| Why | Reliable tool (function) calling and good Arabic; all open-weight models |
| Alternatives | `qwen2.5:3b` (fast on CPU), `qwen2.5:14b` (smarter, more GPU), `qwen3:8b`, `llama3.1:8b` |

Hosted providers retire models: Groq retired Llama 3.3 70B in August 2026. `LLM_FALLBACK_MODELS`
are tried automatically when the main model is gone, and the **Test AI** button shows the exact
error from the provider.

The app speaks the OpenAI chat-completions protocol, so any server that does too works: Ollama,
vLLM, llama.cpp server, LocalAI, or hosted open models (Groq, OpenRouter, Together, Fireworks).

```env
LLM_PROVIDER=openai_compatible
LLM_BASE_URL=http://ollama:11434/v1
LLM_MODEL=travel-agent
```

## 2. The `travel-agent` model (Ollama Modelfile)

[`ai/Modelfile`](../ai/Modelfile) builds a custom model on top of the base:

* `num_ctx 16384`: Ollama's default context is too short for a system prompt + tool results + a
  whole booking conversation. Without this the model "forgets" what the customer said.
* `temperature 0.3`: precise with prices and dates, still natural.
* A default travel-consultant persona.

`docker compose` runs [`ai/setup-model.sh`](../ai/setup-model.sh) once, which pulls the base model
and runs `ollama create travel-agent`. To switch the base model:

```bash
BASE_MODEL=qwen2.5:14b docker compose run --rm ollama-setup
```

## 3. The travel-sales prompt (per company)

[`backend/app/ai/prompts.py`](../backend/app/ai/prompts.py) builds the system prompt for every
reply from:

* the company name and the **agent name** (e.g. "Sara", "Layla"),
* the sales method: understand the trip → search → recommend ≤ 3 → details → collect travelers →
  summarise with the total → wait for the customer's confirmation → create the ticket → hand over,
* strict rules: only offer what the tools return, never take payments, never promise a confirmed
  booking, hand over to a human when needed, stay on topic, reply in the customer's language,
  WhatsApp-friendly formatting,
* the company's **Knowledge & policies** (deposit, cancellation, visas, office hours…) and
  **Extra instructions**, both editable by the company admin in **AI & WhatsApp**,
* what we already know about the customer (e.g. the phone number on WhatsApp).

## 4. Training: how a company teaches the AI

Without retraining the model, each company shapes its AI with:

* **Packages**: titles, descriptions, inclusions and tags (Arabic tags such as «شهر عسل» or
  «صلالة» let Arabic questions find the right trips).
* **Knowledge & policies** and **Extra instructions** (AI & WhatsApp page).
* **AI training** page: questions with the company's approved answers. For every customer message
  the 3 closest questions (Arabic or English, by keywords) are added to the prompt, so the AI
  answers the company's way.
* Built-in travel-consultant skills in the prompt: needs discovery, family/honeymoon/Umrah tips,
  passport and insurance reminders, honest budget suggestions, Gulf Arabic style, Omani rial prices.

A company's training is used only for that company. Real fine-tuning of the shared model on
company chats is deliberately not done: it could leak one company's information to another
company's customers.

## 5. Tools (grounding)

[`backend/app/ai/tools.py`](../backend/app/ai/tools.py)

| Tool | What it does |
|---|---|
| `search_packages(query, max_price_per_person, min_days, max_days, departure_month)` | Ranked search over the company's bookable packages (active, seats left, future dates). Suggests alternatives when nothing matches. |
| `get_package_details(package_id)` | Description, inclusions, exclusions, hotel, upcoming departures. |
| `create_booking_ticket(...)` | Validates the package, date, seats and contact details; **computes the price on the server**; creates the ticket (`waiting for payment`); hands the conversation to the team. |
| `request_human_agent(reason)` | Hands the conversation to an employee. |

Tools receive the company and conversation from the server, never from the model, so a customer
cannot make the AI read or book another company's data, whatever they type.

## 6. The agent loop

[`backend/app/ai/agent.py`](../backend/app/ai/agent.py): model → tools → model … (max 6 rounds) →
reply. Tool calls and results are stored with the conversation so the AI remembers earlier search
results on the next message, and employees can see exactly what the AI did ("Show AI tool
activity"). Robustness for small open models:

* tool calls written as JSON text instead of the tool channel are recovered,
* hidden `<think>` reasoning (Qwen 3, DeepSeek-R1) is removed,
* broken tool sequences are dropped from the history,
* if the model is unreachable or produces nothing, the customer gets a polite reply and the
  conversation is handed to a human. A ticket created before a failure is kept.

## 7. Going further

* **Fine-tuning**: export good conversations (staff can see them all) as chat-format JSONL and
  fine-tune with LoRA (e.g. Unsloth/Axolotl) on top of the base model, then import the GGUF into
  Ollama with a `FROM ./model.gguf` Modelfile. The prompt and tools stay the same.
* **Bigger catalogs**: the search tool ranks in Python, which is fine for hundreds of packages per
  company. For thousands, add PostgreSQL full-text search or embeddings (pgvector).
