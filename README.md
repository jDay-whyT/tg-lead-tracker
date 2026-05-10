# tg-lead-tracker

Telegram bot that monitors HR managers' personal chats via the Business Bot API. When a new user messages a manager, the bot logs it as a lead to Google Sheets.

## How it works

1. HR manager connects the bot via Telegram → Settings → Chat Automation
2. Bot notifies admin and waits for approval
3. Once approved, every incoming message from a new contact is logged to Google Sheets
4. Duplicate leads (same user, same manager) are skipped automatically

## Stack

- **Python 3.12** + python-telegram-bot v21
- **FastAPI** + uvicorn (webhook server)
- **Google Cloud Run** (hosting)
- **Google Firestore** (manager registry + lead deduplication)
- **Google Sheets API** (lead log)
- **Application Default Credentials** (no key files)

## Setup

### 1. Clone and configure

```bash
git clone https://github.com/jDay-whyT/tg-lead-tracker.git
cd tg-lead-tracker
cp .env.example .env
```

Fill in `.env`:

| Variable | Description |
|---|---|
| `BOT_TOKEN` | Telegram bot token from @BotFather |
| `ADMIN_CHAT_ID` | Your Telegram user ID (receives approval requests) |
| `GOOGLE_SHEETS_ID` | ID from the spreadsheet URL |
| `FIRESTORE_PROJECT_ID` | GCP project ID |
| `WEBHOOK_SECRET` | Optional — passed to Telegram's `setWebhook` |

### 2. Google Sheets

Create a sheet named `Leads` with this exact header row in row 1:

```
DATE | TIME | HR | @user | NAME | ID | TEXT
```

Column order can be changed — the bot reads the header at startup and maps values by name.

### 3. GCP service account

Assign a service account to the Cloud Run service with these roles:
- `roles/datastore.user` (Firestore)
- `roles/sheets.writer` (Sheets, or share the spreadsheet with the SA email)

## Deployment

Deployment is via GitHub Actions (`.github/workflows/deploy.yml`, `workflow_dispatch`).

Required GitHub secrets:

| Secret | Value |
|---|---|
| `GCP_PROJECT` | GCP project ID |
| `GCP_REGION` | e.g. `europe-west1` |
| `CLOUD_RUN_SERVICE` | e.g. `tg-lead-tracker` |
| `GOOGLE_SERVICE_ACCOUNT` | Service account JSON (for CI auth only) |
| `BOT_TOKEN` | |
| `ADMIN_CHAT_ID` | |
| `GOOGLE_SHEETS_ID` | |
| `FIRESTORE_PROJECT_ID` | |
| `WEBHOOK_SECRET` | |

After deploy, register the webhook:

```
https://api.telegram.org/bot{TOKEN}/setWebhook?url={CLOUD_RUN_URL}/webhook&secret_token={WEBHOOK_SECRET}
```

## Admin commands

| Command | Description |
|---|---|
| `/managers` | List all managers with status and connection date |

## Lead deduplication

First message from a lead is logged. Subsequent messages from the same user to the same manager are silently ignored. Dedup state lives in Firestore (`leads` collection) and persists across restarts.
