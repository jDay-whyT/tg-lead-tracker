# TG Lead Tracker — Planning & Architecture

## Overview
A Telegram bot that monitors HR managers' accounts via Chat Automation (Business Bot API).
When a new unknown user messages a manager, the bot logs it to Google Sheets as a lead.
One bot, one codebase, multiple HR accounts — change logic once, applies to all.

## Stack
- **Runtime:** Python 3.12
- **Bot framework:** python-telegram-bot v20+ (webhook mode)
- **Hosting:** Google Cloud Run
- **Database:** Google Firestore (manager registry)
- **Spreadsheet:** Google Sheets API (lead log)
- **Secrets:** Google Cloud Secret Manager or env vars

## Architecture

```
Lead writes to manager (Telegram personal chat)
        ↓
Telegram sends business_message update to webhook
        ↓
Cloud Run receives POST → main.py handler
        ↓
Lookup business_connection_id in Firestore
        ↓
If manager is approved → write row to Google Sheets
```

## Telegram API Key Concepts
- `business_connection` update — fired when a manager connects/disconnects the bot via Settings → Chat Automation
- `business_message` update — fired for every message in manager's personal chats (both directions)
- To detect incoming lead: `message.from_user.id != manager.user_id`
- No Telegram Premium required for Chat Automation (launched May 7, 2026)

## Firestore Schema

### Collection: `managers`
```
document id: business_connection_id (string)
fields:
  user_id: int
  username: string
  first_name: string
  status: "pending" | "approved" | "rejected"
  connected_at: timestamp
```

## Google Sheets Schema
Sheet name: `Leads`
| date | time_utc | manager_username | lead_username | lead_name | lead_user_id | message_preview |
|------|----------|-----------------|---------------|-----------|--------------|-----------------|

## Bot Flows

### 1. Manager Registration
1. Manager connects bot via Settings → Chat Automation
2. Bot receives `business_connection` update
3. Bot saves manager to Firestore with `status: pending`
4. Bot sends admin (ADMIN_CHAT_ID) a message:
   ```
   New manager connected:
   @username | First Name | user_id: 123456
   [Approve ✅] [Reject ❌]
   ```
5. Admin taps button → bot updates Firestore status
6. Bot notifies manager: "You are approved ✅" or "Access denied ❌"

### 2. Lead Logging
1. Bot receives `business_message`
2. Check: `message.from_user.id != manager.user_id` → this is an incoming lead
3. Lookup manager by `business_connection_id` in Firestore
4. If `status != approved` → skip
5. Append row to Google Sheets

### 3. Admin Commands (optional, via direct message to bot)
- `/managers` — list all managers with status
- `/stats` — count of leads per manager (last 7 days)

## Project File Structure
```
tg-lead-tracker/
├── main.py              # Entry point, webhook server (FastAPI or aiohttp)
├── bot/
│   ├── handlers.py      # business_connection, business_message, callback_query handlers
│   ├── admin.py         # Admin approval flow
│   └── sheets.py        # Google Sheets append logic
├── db/
│   └── firestore.py     # Firestore read/write helpers
├── config.py            # Env vars loading
├── Dockerfile           # Cloud Run container
├── requirements.txt
├── .env.example
└── PLANNING.md          # This file
```

## Env Vars
```
BOT_TOKEN=
ADMIN_CHAT_ID=
GOOGLE_SHEETS_ID=
GOOGLE_CREDENTIALS_JSON=   # service account JSON as string
FIRESTORE_PROJECT_ID=
WEBHOOK_SECRET=            # optional, for webhook validation
```

## Deployment (Google Cloud Run)
1. Build Docker image
2. Push to Google Artifact Registry
3. Deploy to Cloud Run (min instances: 1 to avoid cold start on webhook)
4. Set webhook: `https://api.telegram.org/bot{TOKEN}/setWebhook?url={CLOUD_RUN_URL}`

## Roadmap
- [x] Architecture defined
- [ ] Project scaffold & dependencies
- [ ] Firestore helpers
- [ ] business_connection handler + admin approval
- [ ] business_message handler + Sheets logging
- [ ] Dockerfile + Cloud Run config
- [ ] Deploy & set webhook
- [ ] Test with real manager account
