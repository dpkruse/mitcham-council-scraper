# Web App — Deploy Checklist

Work through these steps in order. Each section must be complete before moving to the next.

---

## 1. Doppler — secrets manager

- [ ] Sign up at [doppler.com](https://doppler.com) (free)
- [ ] Install the CLI — download the Windows installer from the Doppler docs
- [ ] Run `doppler login` in a terminal
- [ ] Create a new project called `mitcham-council-docs`
- [ ] In the `production` environment, add these four secrets:

| Key | Where to find the value |
|-----|------------------------|
| `SUPABASE_URL` | Supabase → project Settings → API → Project URL |
| `SUPABASE_SERVICE_KEY` | Supabase → project Settings → API → service_role key |
| `RESEND_API_KEY` | Resend → API Keys |
| `FROM_EMAIL` | The verified sender address you set up in Resend |

---

## 2. Supabase — database and file storage

- [ ] Sign up at [supabase.com](https://supabase.com) (free)
- [ ] Create a new project (choose the Sydney region — closest to Mitcham)
- [ ] Open the **SQL Editor** and run:

```sql
create table requests (
  id            bigserial primary key,
  email         text        not null,
  meeting_id    text        not null,
  meeting_title text        not null,
  meeting_url   text        not null,
  requested_at  timestamptz not null default now(),
  status        text        not null default 'pending',
  ip_address    text
);

-- No public read access — service role key only
alter table requests enable row level security;
```

- [ ] Go to **Storage** → New bucket
  - Name: `meeting-docs`
  - Public: **off** (private)

---

## 3. Resend — email delivery

- [ ] Sign up at [resend.com](https://resend.com) (free — 3,000 emails/month)
- [ ] Add and verify a sending domain (e.g. `mail.yourdomain.com`)
  - Adds three DNS records to your domain — your domain registrar's help docs will show how
  - OR use Resend's shared sender (`onboarding@resend.dev`) while testing — no domain needed
- [ ] Create an API key (API Keys → Add API key)
- [ ] Decide on your `FROM_EMAIL` value (e.g. `noreply@mail.yourdomain.com`)

---

## 4. Render — hosting

- [ ] Sign up at [render.com](https://render.com) (free)
- [ ] New → **Web Service** → connect your GitHub repo (`mitcham-council-scraper`)
- [ ] Render will detect `render.yaml` automatically — confirm the settings look correct
- [ ] Connect Doppler to Render:
  - In Doppler: **Integrations** → Render → Authorise → select the `mitcham-council-docs` service
  - Doppler will now sync secrets to Render automatically on every deploy
- [ ] Trigger a manual deploy and watch the build logs

---

## 5. Local test (before deploying)

Run this in the repo root after completing steps 1–3:

```bash
doppler run -- uvicorn app:app --reload
```

Then open `http://localhost:8000` and verify:

- [ ] Meeting list loads from the CivicClerk portal
- [ ] Selecting a meeting and entering an email enables the Generate button
- [ ] Submitting a job runs through all progress stages without error
- [ ] Email arrives with correct documents and working download links
- [ ] Running the same meeting a second time completes in ~5 seconds (cache hit)
- [ ] Submitting 5 requests from a non-council email → 6th is blocked with a rate-limit message
- [ ] A `@mitchamcouncil.sa.gov.au` address is never rate-limited
- [ ] No API endpoint (`/api/meetings`, `/api/jobs/*`) returns email addresses or the request log

---

## 6. Production smoke test

After Render deploy completes:

- [ ] Visit the `.onrender.com` URL in a browser (no Python installed)
- [ ] Repeat the email and download test on a phone
- [ ] Share the URL with one other councillor or staff member and confirm it works for them

---

## Notes

- **Cold starts:** The free Render tier spins down after 15 min idle. The first request after
  that takes ~30 seconds to wake the server. The UI already shows a notice when this happens.
- **Cache:** Generated PDFs are stored permanently in Supabase Storage keyed by meeting ID.
  To force a re-scrape of a meeting, delete its folder in the Supabase Storage browser.
- **Sender domain:** Using Resend's shared sender is fine for internal testing. Set up a proper
  domain before sharing with residents so the email doesn't show "via resend.dev".
- **Admin log:** To view the request log, go to Supabase → Table Editor → `requests`.
  It is not exposed through any public endpoint.
