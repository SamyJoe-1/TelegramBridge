# Telegram Userbot Bridge — Setup

Posts messages with animated `custom_emoji` entities to a Telegram
**channel**, by automating your **personal Premium account** (MTProto),
triggered from n8n. Bypasses the Bot API restriction that channels need
a Fragment username.

## 1. Get API credentials
Go to https://my.telegram.org → API Development Tools → create an app.
You'll get `api_id` and `api_hash`.

## 2. Generate a session string (one time, interactive)
```bash
pip install telethon
python login.py
```
Enter your `api_id`, `api_hash`, phone number, the login code Telegram
sends you, and your 2FA password if you have one. It prints a session
string — copy it.

## 3. Configure secrets
```bash
cp .env.example .env
# edit .env: TG_API_ID, TG_API_HASH, TG_SESSION_STRING, BRIDGE_API_KEY
```
`BRIDGE_API_KEY` is any long random string you invent — it's what n8n
sends in the `X-API-Key` header so the service isn't an open relay.

## 4. Run it
Locally:
```bash
docker compose up --build -d
```
Check it's alive: `GET http://localhost:8000/health` → `{"status":"ok"}`

If n8n is cloud-hosted (n8n.cloud), this container needs a public HTTPS
URL — put it behind a reverse proxy (Caddy/nginx/Traefik) or a tunnel
(Cloudflare Tunnel, ngrok) with TLS. Don't expose it without the API
key check.

## 5. Get custom_emoji_id values
Forward a message containing the emoji to `@JsonDumpBot` on Telegram —
it returns the raw entities including `custom_emoji_id`. Build a small
lookup table (emoji name → id) for reuse.

## 6. Import the n8n workflow
In n8n: **Workflows → Import from File** → select `n8n-workflow.json`.
Then edit the "Call Userbot Bridge" node:
- Replace `https://YOUR-BRIDGE-HOST/send-message` with your real URL.
- Replace `YOUR_BRIDGE_API_KEY_HERE` with the same value as
  `BRIDGE_API_KEY` in `.env`.
  (Better for production: delete that header parameter and instead
  attach an n8n **HTTP Header Auth** credential so the key isn't sitting
  in plain text inside the workflow JSON.)

The workflow exposes its own webhook: `POST /webhook/send-animated-emoji`
on your n8n instance, expecting:
```json
{
  "chat_id": "@your_channel",
  "text": "Hello world 🎉",
  "entities": [
    {"type": "custom_emoji", "offset": 12, "length": 2, "custom_emoji_id": "5432101234567890123"}
  ]
}
```
It calls the bridge, then responds `200` with `message_id` on success,
or `502` with an error message on failure — so you can chain this
webhook from anywhere (another workflow, a form, a schedule, etc.).

## Operational notes
- **Rate limits**: this is a real user account, not a bot — keep send
  frequency low and human-like. `main.py` already surfaces
  `FloodWaitError` as HTTP 429 so you can add retry/backoff in n8n.
- **Session death**: if the session gets invalidated (password change,
  remote logout, Telegram flags it), `/health` returns `"unauthorized"`.
  Re-run `login.py` and update `TG_SESSION_STRING`. Consider polling
  `/health` on a schedule and alerting yourself (Slack/email node in
  n8n) if it flips.
- **ToS**: automating a personal account this way is more restricted
  under Telegram's terms than bot automation. This is your account and
  your call, but keep volume low.
