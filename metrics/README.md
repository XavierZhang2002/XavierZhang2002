# Profile metrics

The two badges at the top of the profile README are generated here.

- [`.github/scripts/update_metrics.py`](../.github/scripts/update_metrics.py) collects the
  Google Scholar citation count through the SerpApi `google_scholar_author` engine and the
  star total of the repositories listed in [`config.json`](config.json).
- It writes [`stats.json`](stats.json) plus light and dark SVG badges
  (`citations.svg`, `citations-dark.svg`, `project-stars.svg`, `project-stars-dark.svg`).
- [`profile-metrics.yml`](../.github/workflows/profile-metrics.yml) runs twice a day and
  commits whatever changed. The README picks the right variant with
  `<picture>` and `prefers-color-scheme`.
- A failed request keeps the previous snapshot, so a badge never drops to zero; the job only
  fails when there has never been a valid snapshot.

Required secret: `SERPAPI_KEY` (Settings → Secrets and variables → Actions).
`SCHOLAR_ID` is optional and overrides `config.json` when set.
