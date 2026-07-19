# Procore Quality Dashboard

A dashboard of **quality inspections and FAIs (First Article Inspections)** across
all active projects for a Procore company — starting with **United Renewable
Energy, LLC**.

Open `dashboard.html` in any browser. It has four tabs: **Overview** (one row per
active project with its latest inspection + quality/FAI counts), **Quality
Inspections**, **FAIs**, and **All Inspections**.

## Important: two data sources, two levels of coverage

Procore inspections are internally "checklist lists," and there is no single
inspection type called "FAI" — FAIs and quality inspections are distinguished by
their **template / type name**. This tool classifies them by keyword
(configurable in `data.json` → `classification`):

- **FAI**: name/template/type contains `fai` or `first article`
- **Quality**: contains `quality`, `qa/qc`, `qaqc`, or `qc`
- everything else → **Other**

### 1. Zapier snapshot (what ships in `data.json` today)

The committed `data.json` was pulled live from Procore **through the Zapier
connection**. That connection is a *polling trigger*: it returns only the
**single most-recent inspection per project**. Across the projects sampled, every
latest record was a Safety or Commissioning inspection, so the Quality and FAI
tabs are sparse — **not because those inspections don't exist, but because the
trigger can't reach past each project's newest record.** The dashboard shows a
banner saying so.

Use this for a quick portfolio + latest-status view. Do **not** treat the
Quality/FAI counts here as complete.

### 2. Procore REST API (full history — recommended)

`fetch_procore.py` pulls the **complete** inspection history per project directly
from the Procore REST API, with no latest-only limit. This is the only way to get
accurate Quality and FAI coverage.

```bash
export PROCORE_ACCESS_TOKEN=...      # OAuth 2.0 bearer token (read: projects, checklists)
export PROCORE_COMPANY_ID=48607      # United Renewable Energy, LLC
# optional:
export PROCORE_BASE_URL=https://api.procore.com   # or https://sandbox.procore.com
export PROCORE_COMPANY_NAME="United Renewable Energy, LLC"

python3 fetch_procore.py   # overwrites data.json with full history
python3 render.py          # rebuilds dashboard.html
```

Get a token by creating an app in the [Procore Developer
Portal](https://developers.procore.com/) (a Data Connection / service account, or
the authorization-code flow). The exact checklist endpoint version and
inspection-type field names can vary by company configuration — adjust the
`ENDPOINTS`/field mapping in `fetch_procore.py` if your org returns a different
shape.

## Files

| File | Purpose |
|------|---------|
| `dashboard.html` | The rendered dashboard. Open this. Self-contained (no external assets). |
| `data.json` | The data behind the dashboard. Currently the Zapier snapshot. |
| `fetch_procore.py` | Pulls full inspection history from the Procore REST API → `data.json`. |
| `render.py` | Renders `data.json` → `dashboard.html`. No dependencies. |

## Scope

Company: United Renewable Energy, LLC (`48607`). 39 active projects (templates and
sandboxes — `X -`, `XX -`, `Y -`, `ZZ -`, `2026 Pursuits` — are excluded). To
cover the other companies in the account (Aldridge Electric, GS Power Partners,
Pivot Energy, Beitzel, Duke Energy Generation - PMC, Premise), run
`fetch_procore.py` again with a different `PROCORE_COMPANY_ID`.
