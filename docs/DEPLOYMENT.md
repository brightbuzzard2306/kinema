# Deploying Kinema

```
 visitor's browser
      │  https://kinema.co.in                 https://api.kinema.co.in
      ▼                                         ▲
  Vercel  (the website: Next.js)  ── API calls ─┘  Render  (the recommender: FastAPI in Docker)
                                                      │            │
                                                      ▼            ▼
                                              Anthropic API     TMDB (posters)
```

Two free services, two small jobs: **Vercel** serves the pages, **Render** runs the recommender. They are tied together by two settings:
the website needs to know the API's address (`NEXT_PUBLIC_API_URL`), and the API needs to know which website may call it (`FRONTEND_ORIGIN`).

Do the steps in this order. Use the **college** GitHub account (`brightbuzzard2306`) for every sign-up below, never the personal one.
Secrets (API keys, the access code) are typed into the dashboards by you; they are never in the repository.

---

## 1. The API on Render (about 15 minutes, most of it waiting)

1. Go to <https://render.com> → **Get Started** → **Sign in with GitHub** (college account) and allow access to the `kinema` repository.
2. **New +** → **Web Service** → **Build and deploy from a Git repository** → choose `brightbuzzard2306/kinema`.
3. Fill in:

   | Field | Value |
   |---|---|
   | Name | `kinema-api` |
   | Region | **Singapore** (closest to India) |
   | Branch | `main` |
   | Language / Runtime | **Docker** |
   | Dockerfile Path | `./backend/Dockerfile` |
   | Docker Build Context Directory | `.` (a single dot: the repository root) |
   | Instance Type | **Free** |

4. Open **Advanced** and set **Health Check Path** to `/health`.
5. Still under **Environment Variables**, add these (click *Add Environment Variable* for each):

   | Name | Value | Notes |
   |---|---|---|
   | `ACCESS_CODE` | a word or phrase **you choose** | The password visitors type. Share it only with who should see the site. |
   | `ANTHROPIC_API_KEY` | your key | Paste it here; never anywhere else. |
   | `ANTHROPIC_WORKSPACE_ID` | the `wrkspc_…` value from your local `.env` | Your key needs it (it did locally). Skip only if your `.env` has no such line. |
   | `CLAUDE_MODEL` | `claude-haiku-4-5` | Fast and cheap. Same as local. |
   | `TMDB_API_KEY` | your TMDB key | Optional; without it posters are typographic. |
   | `FRONTEND_ORIGIN` | `https://kinema.co.in,https://www.kinema.co.in` | Comma-separated. You will add the Vercel preview address here in step 2. |
   | `CLAUDE_DAILY_LIMIT` | `400` | Optional. Claude calls per day for the whole site (a chat turn uses 2). After that the site says "offline mode" until tomorrow (UTC). |

6. **Create Web Service**. The first build takes 5–10 minutes (it installs the libraries and downloads MovieLens).
7. When the log says *Your service is live*, open `https://kinema-api.onrender.com/health` (use the address Render shows at the top). You should see JSON starting with `{"status":"ok"`.

> **What "free" means here.** Render puts a free service to sleep after 15 minutes without traffic; waking it takes up to about a minute and a half.
> The website shows a "Waking the server up" message instead of an error while that happens. Step 4 (UptimeRobot) keeps it awake.
> Conversations are stored on the server's disk, which free instances lose on every restart or redeploy; people then simply start a fresh chat.

---

## 2. The website on Vercel (about 5 minutes)

1. Go to <https://vercel.com/signup> → **Continue with GitHub** (college account).
2. **Add New… → Project** → import `brightbuzzard2306/kinema`.
3. **Root Directory → Edit → `frontend`** (important: the website lives in that folder). Framework should read *Next.js*.
4. Open **Environment Variables** and add:

   | Name | Value |
   |---|---|
   | `NEXT_PUBLIC_API_URL` | `https://api.kinema.co.in` |
   | `NEXT_PUBLIC_AUTHOR` | your name |
   | `NEXT_PUBLIC_COLLEGE` | your college |
   | `NEXT_PUBLIC_COURSE` | e.g. `Recommendation Systems · Mini Project` |
   | `NEXT_PUBLIC_GUIDE` | your guide's name |

   (The last four are optional; blank means the credit line is hidden. These values are public by design.)
5. **Deploy**. When it finishes Vercel shows an address like `kinema-xxxx.vercel.app`.
6. Go back to Render → your service → **Environment** → edit `FRONTEND_ORIGIN` and add that Vercel address:
   `https://kinema.co.in,https://www.kinema.co.in,https://kinema-xxxx.vercel.app`. Render restarts the service.

> The website will not work until step 3 is done, because `api.kinema.co.in` does not exist yet. That is expected.

---

## 3. Your domain `kinema.co.in` (GoDaddy)

You do three things: tell Render and Vercel about the names, then create matching records at GoDaddy.

**A. Render:** your service → **Settings → Custom Domains → Add Custom Domain** → `api.kinema.co.in`. Render shows a record to create (type **CNAME**, name `api`, value like `kinema-api.onrender.com`).

**B. Vercel:** your project → **Settings → Domains** → add `kinema.co.in`, then add `www.kinema.co.in` (choose *Redirect to kinema.co.in*). Vercel lists the records it wants. Typically:

| Type | Name | Value |
|---|---|---|
| A | `@` | `76.76.21.21` |
| CNAME | `www` | `cname.vercel-dns.com` |

Always copy the values Vercel shows you; if they differ from the table, Vercel's are right.

**C. GoDaddy:** sign in → **My Products** → next to `kinema.co.in` choose **DNS** (Manage DNS).
1. Delete the default **A** record for `@` that says *Parked* and the default **CNAME** for `www` (they conflict with the new ones). If the page has a **Forwarding** section for this domain, remove it too.
2. **Add** the three records: `A @` → Vercel's IP, `CNAME www` → Vercel's value, `CNAME api` → Render's value (for example `kinema-api.onrender.com`, without `https://`).
3. Save. TTL can stay at the default.

**D. Wait and verify.** DNS usually works within minutes, sometimes up to an hour. Vercel and Render show a green tick next to each domain once it works and issue the HTTPS certificates by themselves. Then open <https://kinema.co.in>: you should see the "This one is private" screen.

---

## 4. Keep the API awake (UptimeRobot, 5 minutes)

1. <https://uptimerobot.com> → sign up (a college email is fine) → **Add New Monitor**.
2. Monitor type **HTTP(s)**, name `Kinema API`, URL `https://api.kinema.co.in/health`, interval **5 minutes**.
3. Create. As a bonus it emails you if the API goes down.

Render's free plan gives 750 hours a month, enough to keep one service awake 24/7, as long as this is the only free web service in that Render account.

---

## 5. Protect the Claude budget (2 minutes)

In <https://console.anthropic.com> open the workspace the key belongs to → **Limits** → set a **monthly spend limit** you are comfortable with. This is the real hard stop; the site's own daily cap and rate limits are extra safety.

What the site already does by itself:
* needs the access code for everything except `/health`;
* limits each visitor to 20 chat/recommend requests and 240 other requests per minute;
* stops Claude calls after `CLAUDE_DAILY_LIMIT` per day and falls back to the offline parser;
* locks a visitor out for 10 minutes after 8 wrong codes.

---

## 6. Day-to-day

| I want to… | Do this |
|---|---|
| Change the code | Edit the files, `git commit`, `git push` (as the college account). Vercel and Render redeploy by themselves. |
| Change the access code | Render → Environment → edit `ACCESS_CODE` → save. Everyone is asked for the new one. |
| Replace an API key | Render → Environment → edit the value → save. |
| Change the name/college text | Vercel → Settings → Environment Variables → edit → **Redeploy** (these are baked in at build time). |
| See what went wrong | Render → your service → **Logs**. Logs never contain chat text or keys. |

## 7. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| "Waking the server up" for a long time | Normal after idle; up to ~90 s. If it never ends, open `https://api.kinema.co.in/health` directly and read Render's logs. |
| Website loads but says it can't reach the recommender | `NEXT_PUBLIC_API_URL` wrong (it must be `https://…`, no trailing slash) → fix on Vercel and **Redeploy**; or the domain's tick on Render is not green yet. |
| Browser console shows a CORS error | `FRONTEND_ORIGIN` on Render is missing the exact address you are visiting (https, no trailing slash). |
| Everyone sees "offline mode" | Render logs / the badge reason: key rejected, workspace not set, or the daily cap was reached. |
| "That code isn't right" with the right code | `ACCESS_CODE` has stray spaces, or you changed it recently: type exactly what is in Render. |
| Build fails on "Could not download MovieLens" | A temporary network hiccup (it retries four times). Press **Manual Deploy → Deploy latest commit**. |
| Domain still shows GoDaddy's parked page | The old `A @` record is still there, or Forwarding is on. Remove them. |

## 8. Honest limits of this setup

* Free hosting: cold starts after idle (mitigated by UptimeRobot), conversations lost on redeploy.
* One instance only: rate limits and the daily Claude cap are per instance (fine here, they would need shared storage to scale out).
* The access code is a shared password, not per-user accounts.
* Memory: the API uses about 230 MB of Render's 512 MB (measured in a container limited to 512 MB and 0.1 CPU).
