# Putting this app on your Wix website

This app is a **Python (Flask) web application**. Wix is a website builder that
**cannot run Python on its own**, so the approach is:

1. **Host** the Python app on a service that runs Python (one-time setup).
2. **Embed** that hosted app inside a Wix page using an iframe.

Your visitors stay on your Wix site and run the optimizer right there in the page.

---

## Step 1 — Put the code on GitHub

1. Create a free account at <https://github.com> if you do not have one.
2. Create a new repository (e.g. `structural-optimization-studio`).
3. Upload **all the files in this folder** (engine.py, app.py, thumbs.py,
   requirements.txt, Procfile, render.yaml, the `templates/` and `static/`
   folders — keep the structure identical).

(You can do this through the GitHub website with "Add file → Upload files".)

---

## Step 2 — Host it for free on Render.com

Render runs Python apps directly and has a free tier.

1. Sign up at <https://render.com> and connect your GitHub account.
2. Click **New + → Blueprint**, pick your repository. Render reads the included
   `render.yaml` and configures everything automatically. *(Alternatively choose
   **New + → Web Service** and set the start command to:
   `gunicorn app:app --workers 1 --threads 8 --timeout 180 --bind 0.0.0.0:$PORT`)*
3. Wait for the build to finish. Render gives you a public URL like
   **`https://structural-optimization-studio.onrender.com`** — open it to confirm
   the app loads.

> The included `render.yaml` already sets `EMBED_ALLOW="*"`, which lets your Wix
> page frame the app. To restrict it to only your site, change that value to your
> Wix domain, e.g. `https://www.yoursite.com`.

Other hosts work the same way (Railway, Fly.io, PythonAnywhere). Any host that
runs a Flask/Gunicorn app is fine — the app only needs Python, NumPy and SciPy.

---

## Step 3 — Embed it in your Wix page

1. In the **Wix Editor**, open the page where you want the optimizer.
2. Click **Add (+) → Embed Code → Embed a Site** (the "Embed a Site / iframe"
   element).
3. In its settings, paste your hosted URL from Step 2
   (e.g. `https://structural-optimization-studio.onrender.com`).
4. Drag the element to fill the page and stretch it to full width. A tall frame
   (around 900–1200 px, or full-screen) works best so the 3D model and tables
   have room.
5. **Publish** your Wix site. Visitors can now run the optimizations inside your
   page.

### Tip — a cleaner full-screen option
Instead of an iframe you can add a **button** in Wix that links to the hosted URL
(open in a new tab), or point a **subdomain** such as
`optimize.yoursite.com` at the Render service (Render → Settings → Custom Domain).
This avoids iframe size constraints and gives the app the whole screen.

---

## Notes for a public audience

- **Free tiers sleep.** On Render's free plan the app "spins down" after ~15 min
  of inactivity; the next visit takes ~30–60 s to wake. A paid plan (a few dollars
  a month) keeps it always-on.
- **Concurrency.** The app caps simultaneous optimizations (default 6, set by the
  `MAX_RUNNING_JOBS` env var) and shows a friendly "server busy" message beyond
  that, so one visitor cannot overwhelm it. Heavier traffic just needs a larger
  paid instance.
- **Cost.** NumPy/SciPy only; no database, no GPU. The smallest instance is plenty
  for teaching/learning use.

---

## Alternative — run it fully inside the browser (no hosting)

Because the app depends only on NumPy/SciPy, the entire engine can be ported to
run **in the visitor's browser** via Pyodide (Python compiled to WebAssembly).
That turns it into static files Wix can host directly, with no server, no
hosting cost, and no "sleeping". It is a larger rewrite of the front-end. If you
prefer that route, it is the most Wix-native option — ask and it can be built.
