# Putting the app online — free, about 10 minutes

The app is self-contained. It reads a **0.45 MB** bundle in `assets/` and calls a
free weather service. No database, no API key, no paid tier.

---

## Step 1 — put the code on GitHub

The project is already committed locally. You need to create an empty repo on
GitHub, then push:

```bash
cd D:\CODE\BeeDigital\LandSlideFlood
git branch -M main
git remote add origin https://github.com/<your-username>/arunachal-landslide-forecast.git
git push -u origin main
```

Make the repo **public** — the free Streamlit tier requires it.

### ✅ Already checked for you

- Credentials are excluded. `misc/PlatformPasswords.txt` and `.env` are ignored.
  *(The original ignore rule named the wrong folder and would have committed the
  password file — that is fixed.)*
- Repo is **31 MB**. The 11 GB of raw data and 88 MB of GSI PDFs are excluded and
  regenerable from `scripts/fetch/`.

## Step 2 — deploy

1. Go to **<https://share.streamlit.io>** and sign in with GitHub.
2. **Create app → Deploy a public app from GitHub**.
3. Fill in:
   - **Repository:** `<your-username>/arunachal-landslide-forecast`
   - **Branch:** `main`
   - **Main file path:** `webapp/app.py`
4. Deploy.

Build takes ~2 minutes — the dependency list is deliberately tiny (numpy, pandas,
pillow, requests, streamlit). **No rasterio, geopandas or lightgbm**, which is
what keeps it inside the free tier's 1 GB.

Your link will be `https://<app-name>.streamlit.app`. That is the URL for your
profile.

Every push to `main` redeploys automatically.

### Alternative — Hugging Face Spaces

Also free. Create a Space with the **Streamlit** SDK and add to its `README.md`:

```yaml
sdk: streamlit
app_file: webapp/app.py
```

> ⚠️ **Vercel and Netlify will not work.** They serve static files and serverless
> functions; Streamlit needs a long-running process and an open WebSocket.

---

## Updating what the app shows

The deployed app never runs the pipeline. To refresh it:

```bash
# refresh rainfall history (only needed occasionally)
python scripts/fetch/fetch_20_openmeteo_climatology.py

# rebuild the bundle
python scripts/run/export_webapp_bundle.py

git commit -am "Refresh app bundle" && git push     # auto-redeploys
```

If the susceptibility model is retrained, re-run
`scripts/model/predict_susceptibility.py` first.

---

## Running it locally

```bash
pip install -r webapp/requirements.txt
streamlit run webapp/app.py
```

---

## Free-tier fit

| Constraint | This app |
|---|---|
| Repo size | 31 MB (data excluded) |
| Bundle the app loads | **0.45 MB** |
| Memory | well under 1 GB — a few small arrays |
| Build time | ~2 min, 5 slim dependencies |
| API keys | none — Open-Meteo is keyless |
| Live API calls | **3 per hour**, regardless of traffic (1-hour cache) |

## ⚠️ Two things to know before sharing the link

**Open-Meteo's free tier is for non-commercial use.** Fine for a portfolio piece.
If this ever goes to a paying client, move to a paid tier — see
[RAINFALL_RESOLUTION_LIMITS.md](../docs/design/RAINFALL_RESOLUTION_LIMITS.md),
which also restores full 11 km rainfall detail.

**The app says "not for operational safety decisions" and should keep saying it.**
The score is a relative ranking, not a probability, and rainfall is sampled at
~33 km.
