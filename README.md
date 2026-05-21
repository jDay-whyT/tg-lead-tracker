# tg-lead-tracker

Telegram bot that monitors HR managers' personal chats via the Business Bot API. When a new contact messages a manager, the bot logs it as a lead to Google Sheets. When the manager replies, the contact timestamp is written back to the same row.

## How it works

1. HR manager connects the bot via Telegram → Settings → Chat Automation
2. Bot prompts the manager to enter their CRM nickname
3. Admin receives an approval request with CRM nickname, @username, user_id
4. Once approved, every first incoming message from a new contact is logged to Google Sheets
5. When the manager replies to that contact, `Дата связи` column is filled automatically
6. Duplicate leads (same user, same manager) are skipped

## Stack

- **Python 3.12** + python-telegram-bot v21
- **FastAPI** + uvicorn (webhook server)
- **Google Cloud Run** (hosting)
- **Google Firestore** (manager registry + lead deduplication + lego state)
- **gspread** (Google Sheets read/write — lighter than google-api-python-client)
- **Application Default Credentials** (no key files)

## Registration flow

```
Manager connects bot (Chat Automation)
        ↓
Bot asks: "Привет! Введи свой CRM ник"
        ↓
Manager replies with CRM nickname
        ↓
Admin receives: CRM ник | @username | user_id  [Approve ✅] [Reject ❌]
        ↓
Manager notified: approved or denied
```

## Lead logging flow

```
Lead messages manager
        ↓
Bot checks: approved manager, new lead (not in Firestore)
        ↓
Writes row to candidates sheet (sparse — only known columns)
Saves row_number to Firestore
        ↓
Manager replies to lead
        ↓
Bot fills Дата связи at saved row_number (once only)
```

## Google Sheets

Sheet name: `candidates`

Columns matched by header name — order in the sheet does not matter. Bot reads the header row at container startup.

| Header | Value |
|---|---|
| `Стейдж HR, точно так,как в CRM` | Manager's CRM nickname |
| `Дата` | Lead's first message timestamp `DD.MM.YY HH:MM` |
| `Telegram` | `@username` or full name if no username |
| `Должность` | `manager` (hardcoded) |
| `Дата связи` | Manager's first reply timestamp `DD.MM.YY HH:MM` |

All other columns are left untouched.

## Lego form import

Separate pipeline that polls Google Sheets forms on a 5-minute Cloud Scheduler schedule via `POST /import/lego`.

Supported sheets (configured in `bot/lego.py`):

| Sheet | Source label | Type |
|---|---|---|
| `YD forma 1` | `YD Lego 1` | YD |
| `YD Smurf` | `YD Smurf` | YD |
| `YD Lego GEO` | from `adset_name` column (e.g. `YD Lego GE`, `YD Lego MD`, `YD Lego RO`, `YD Lego PL`) | YD |
| `Smurf Belgrade ru` | `Smurf BG ru` | Belgrade |

Sheets `OFF`, `OFF2`, `OFF3`, `OFF4` exist in the spreadsheet but are intentionally ignored.

### Lego import flow

```
Cloud Scheduler → POST /import/lego
        ↓
Read all configured sheets (new rows only, by created_time)
Each sheet read is isolated — one failing sheet does not stop others
        ↓
Sort all new rows by created_time (oldest first)
        ↓
For each new row:
  Deduplicate by Telegram handle in candidates sheet
  Assign HR via round-robin (HR_LIST)
  Write row to candidates sheet
  Send Telegram group notification (2s delay between messages)
  Advance state cursor in Firestore
```

State persisted in Firestore (`lego_state/state`): `last_processed_created_time` + `rr_counter`.

Telegram field is normalised on import: `@username` extracted from free-text, phone numbers kept as-is.

Flood control: 2-second sleep between each Telegram message + automatic retry on `RetryAfter` (up to 3 attempts).

---

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
| `ADMIN_CHAT_ID` | Comma-separated Telegram user IDs — `123,456` — receive approval requests and alerts |
| `GOOGLE_SHEETS_ID` | ID from the spreadsheet URL |
| `FIRESTORE_PROJECT_ID` | GCP project ID |
| `WEBHOOK_SECRET` | Optional — validated via `X-Telegram-Bot-Api-Secret-Token` (webhook) and `X-Webhook-Secret` (lego). Startup warning logged if unset. |
| `LEGO_FORM_ID` | Google Sheets ID of the lego forms spreadsheet |
| `HR_LIST` | Comma-separated `Name:@username` pairs — `Mia:@mia_hr,Dima:@dima_hr` |
| `GROUP_CHAT_ID` | Telegram group chat ID for lego lead notifications |

### 2. GCP service account

Assign a service account to the Cloud Run service with:
- `roles/datastore.user` (Firestore)
- Share the `candidates` spreadsheet with the SA email (Editor role)

## Deployment

Via GitHub Actions — `.github/workflows/deploy.yml`, trigger: `workflow_dispatch`.

Required GitHub secrets:

| Secret | Description |
|---|---|
| `GCP_PROJECT` | GCP project ID |
| `GCP_REGION` | e.g. `europe-west1` |
| `CLOUD_RUN_SERVICE` | Cloud Run service name |
| `GOOGLE_SERVICE_ACCOUNT` | Service account JSON (CI deploy auth only) |
| `BOT_TOKEN` | |
| `GOOGLE_SHEETS_ID` | |
| `FIRESTORE_PROJECT_ID` | |
| `WEBHOOK_SECRET` | |

`ADMIN_CHAT_ID` is **not** in deploy.yml — set it directly in Cloud Run environment variables (supports multiple IDs: `123,456`).

After deploy, register the webhook:

```
https://api.telegram.org/bot{TOKEN}/setWebhook?url={CLOUD_RUN_URL}/webhook&secret_token={WEBHOOK_SECRET}
```

## Commands

### Admin only

| Command | Description |
|---|---|
| `/managers` | List all managers with status and connection date |
| `/delete @username` | Remove a manager from Firestore |
| `/help` | List all commands |

Silently ignored for non-admins.

### Manager only

| Command | Description |
|---|---|
| `/reset` | Reset CRM nickname — bot prompts for a new one, re-triggers approval |

## Firestore collections

| Collection | Document ID | Key fields |
|---|---|---|
| `managers` | `business_connection_id` | `user_id`, `username`, `crm_name`, `status`, `connected_at` |
| `leads` | `{connection_id}_{lead_user_id}` | `row_number`, `replied` |
| `lego_state` | `state` | `last_processed_created_time`, `rr_counter` |

Manager statuses: `awaiting_crm_name` → `pending` → `approved` / `rejected` / `disconnected`
