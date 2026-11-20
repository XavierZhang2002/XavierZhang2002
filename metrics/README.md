# Profile metrics

The citation badge in the profile README is refreshed by
[`.github/workflows/scholar-metrics.yml`](../.github/workflows/scholar-metrics.yml).

- `.github/scripts/fetch_scholar.py` queries the Google Scholar author profile through the
  SerpApi `google_scholar_author` engine and writes `results/gs_data.json` plus a
  shields.io-compatible `results/gs_data_shieldsio.json`.
- The workflow force-pushes those two files to the orphan branch
  `google-scholar-stats`, so the README badge can read a stable raw URL.
- If the request fails or returns no citation table, the script exits non-zero and the
  previous snapshot stays published — the badge never drops to zero.
- Scholar ID and the repository list live in [`config.json`](config.json).

Required secret: `SERPAPI_KEY` (Settings → Secrets and variables → Actions).
`SCHOLAR_ID` is optional and overrides `config.json` when set.
