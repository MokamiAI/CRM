# Deploying YGT

YGT runs as five small services on one server: the API, a background
worker, a scheduler, Redis, and Caddy (which serves the web app and gets
HTTPS certificates automatically). The database stays on Supabase.

## Where to host

| Option | Cost (Oct 2026) | Good for |
| --- | --- | --- |
| **Xneelo Cloud** (2 vCPU, 4 GB, Johannesburg) | R198/month + about R1.80/GB disk (≈ R235 with 20 GB), VAT incl., billed hourly | Data in South Africa (simpler POPIA story), low latency, billed in rand. |
| Hetzner Cloud CPX22 (2 vCPU, 4 GB) | about €20/month | Germany/Finland. The cheap CX23 (€6) is mostly out of stock since mid-2026. |
| Render / Railway | free tiers sleep or exclude workers; realistic setups $25–$40+/month | No server to manage, but the worker and Redis cost extra. |

Recommendation: Xneelo Cloud, 2 vCPU / 4 GB with a 20 GB boot volume, with
`docker-compose.prod.yml`. Prices change; check the provider's page before
ordering. Open ports 22, 80 and 443 in the instance's security group.

## What you need

- A server (Ubuntu 24.04) with Docker: `curl -fsSL https://get.docker.com | sh`
- A domain, e.g. `app.ygt.co.za`, with an **A record** pointing at the server.
- Supabase project (already set up; reset the database password first, since
  an old one is in the git history).
- An email-sending service for SMTP (Brevo, Mailgun, Amazon SES, Zoho…), with
  your domain verified so emails don't land in spam.
- Paystack live keys once your business is verified.

## Steps

1. **Copy the code to the server** (the `main` branch: see Development and releases)
   `git clone -b main https://github.com/MokamiAI/CRM.git && cd CRM`
2. **Create `.env`** from `.env.example` and fill in every value. Production
   must-haves:
   - `DATABASE_URL`, `DATABASE_URL_MIGRATIONS` (Supabase, new password)
   - `JWT_SECRET`, `CREDENTIALS_KEY`, `INBOUND_EMAIL_SECRET` (generate new ones)
   - `DOMAIN=app.ygt.co.za`, `FRONTEND_URL=https://app.ygt.co.za`,
     `PUBLIC_API_URL=https://app.ygt.co.za`, `CORS_ORIGINS=["https://app.ygt.co.za","capacitor://localhost","https://localhost"]`
   - `REDIS_URL=redis://redis:6379/0`, `RATE_LIMIT_STORAGE=redis`, `TRUST_PROXY_HEADERS=true`
   - `SMTP_*`, `SUPPORT_EMAIL`, `BOOKING_CALENDAR_EMAIL`, `PLATFORM_ADMIN_EMAILS`.
     `SMTP_FROM_EMAIL` (e.g. `billing@ygt.co.za`) must be on a domain your
     email service has verified: companies that haven't connected their own
     mailbox send through it, showing their company name, with replies going
     to the company.
   - `PAYSTACK_SECRET_KEY`
   - `ENVIRONMENT=production`, `DEBUG=false`
3. **Start everything**
   `docker compose -f docker-compose.prod.yml up -d --build`
   The API runs the database migrations on start. Check:
   `curl https://app.ygt.co.za/health`
4. **Paystack**: dashboard > Settings > API Keys & Webhooks > webhook URL
   `https://app.ygt.co.za/api/v1/public/paystack/webhook`
5. **Legal pages**: fill in your registration number and address in
   `frontend/src/pages/PublicPages.jsx` (`LEGAL`), have Terms/Privacy/Refunds
   reviewed, then rebuild (`docker compose -f docker-compose.prod.yml up -d --build web`).
6. **Sign up** at `https://app.ygt.co.za/register` with the email in
   `PLATFORM_ADMIN_EMAILS`; "YGT admin" appears in your menu.

## Development and releases

Two long-lived branches on GitHub:

| Branch | What it is | Who uses it |
| --- | --- | --- |
| `develop` | Day-to-day work. Every change lands here first. | You and anyone building YGT |
| `main` | What's live. Only tested releases are merged in. | The production server |

1. Work on `develop` (or a short branch off it, merged back with a pull request).
   GitHub runs the tests and the web build on every push (`.github/workflows/ci.yml`).
2. When a release is ready, run the testing guide against a test setup.
3. Open a pull request from `develop` into `main`. Merge it only when the
   checks are green and the testing guide passes.
4. Deploy (below). The server only ever pulls `main`.

An urgent fix for something live: branch off `main`, fix, merge into `main`,
deploy, then merge `main` back into `develop`.

## Updating

```
git pull origin main
docker compose -f docker-compose.prod.yml up -d --build
```

## Keeping it healthy

- **Errors**: the admin site's Error log shows every server error and failed
  background job, per company.
- **Backups**: Supabase's free plan has no point-in-time recovery; upgrade, or
  run a nightly `pg_dump` to storage you control.
- **Logs**: `docker compose -f docker-compose.prod.yml logs -f backend celery_worker`
