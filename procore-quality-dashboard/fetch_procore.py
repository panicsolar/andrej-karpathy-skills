#!/usr/bin/env python3
"""Fetch active projects and their inspections from the Procore REST API.

Writes data.json in the same shape the Zapier snapshot uses, but with the FULL
inspection history per project (not just the latest record). Run render.py
afterwards to rebuild dashboard.html.

Why this exists: the Procore connection exposed through Zapier is a polling
trigger that only returns the single most-recent inspection per project, so it
cannot surface a project's Quality inspections or FAIs if a newer Safety
inspection exists. The REST API has no such limit.

Setup:
  export PROCORE_ACCESS_TOKEN=...        # OAuth 2.0 bearer token
  export PROCORE_COMPANY_ID=48607        # United Renewable Energy, LLC
  # Optional overrides:
  export PROCORE_BASE_URL=https://api.procore.com   # or https://sandbox.procore.com
  python3 fetch_procore.py

Tokens: create a Data Connection / Service account app in the Procore Developer
Portal, or use the authorization-code flow. The token needs read access to
Projects and Inspections (checklists) for the target company.

Endpoint note: Procore inspections are "checklist lists". The exact version
(v1.0 vs v1.1) and inspection-type field names vary by company configuration.
Adjust ENDPOINTS below if your org returns a different shape.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE_URL = os.environ.get("PROCORE_BASE_URL", "https://api.procore.com").rstrip("/")
TOKEN = os.environ.get("PROCORE_ACCESS_TOKEN")
COMPANY_ID = os.environ.get("PROCORE_COMPANY_ID")

# Names/types (lowercased, substring match) that mark an inspection as an FAI or
# a Quality inspection. Kept in sync with data.json -> classification.
FAI_KEYWORDS = ["fai", "first article"]
QUALITY_KEYWORDS = ["quality", "qa/qc", "qaqc", "qc "]

# Project name prefixes that are templates / sandboxes, not real active jobs.
EXCLUDE_PREFIXES = ("X -", "XX -", "Y -", "ZZ -", "2026 Pursuits")


def _get(path, params=None):
    """GET a Procore REST endpoint, returning parsed JSON. Follows page links."""
    url = f"{BASE_URL}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Bearer {TOKEN}")
    req.add_header("Procore-Company-Id", str(COMPANY_ID))
    req.add_header("Accept", "application/json")
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503) and attempt < 3:
                time.sleep(2 ** attempt)
                continue
            body = e.read().decode("utf-8", "replace")
            raise SystemExit(f"HTTP {e.code} on {url}\n{body}")
        except urllib.error.URLError as e:
            if attempt < 3:
                time.sleep(2 ** attempt)
                continue
            raise SystemExit(f"Network error on {url}: {e}")


def _paginate(path, params):
    """Yield rows across all pages using Procore's page/per_page params."""
    params = dict(params)
    params.setdefault("per_page", 100)
    page = 1
    while True:
        params["page"] = page
        rows = _get(path, params)
        if not rows:
            break
        for row in rows:
            yield row
        if len(rows) < params["per_page"]:
            break
        page += 1


def classify(insp):
    """Return 'fai', 'quality', or 'other' for an inspection record."""
    haystack = " ".join(
        str(insp.get(k) or "") for k in ("name", "template_name", "type")
    ).lower()
    if any(k in haystack for k in FAI_KEYWORDS):
        return "fai"
    if any(k in haystack for k in QUALITY_KEYWORDS):
        return "quality"
    return "other"


def fetch_projects():
    """Active projects for the company."""
    projects = []
    for p in _paginate("/rest/v1.1/projects", {"company_id": COMPANY_ID}):
        if p.get("active") is False:
            continue
        name = p.get("name", "")
        if name.startswith(EXCLUDE_PREFIXES):
            continue
        projects.append(
            {
                "id": p.get("id"),
                "name": name,
                "number": p.get("project_number"),
                "stage": (p.get("stage") or {}).get("name") if isinstance(p.get("stage"), dict) else p.get("stage"),
            }
        )
    return projects


def fetch_inspections(project_id):
    """All checklist lists (inspections) for a project."""
    out = []
    for c in _paginate(
        "/rest/v1.0/checklist/lists",
        {"project_id": project_id},
    ):
        insp_type = c.get("inspection_type")
        type_name = insp_type.get("name") if isinstance(insp_type, dict) else insp_type
        template = c.get("template")
        template_name = template.get("name") if isinstance(template, dict) else c.get("template_name")
        out.append(
            {
                "id": c.get("id"),
                "name": c.get("name"),
                "type": type_name,
                "template_name": template_name,
                "status": c.get("status"),
                "inspection_date": c.get("scheduled_date") or c.get("completed_at"),
                "created_date": c.get("created_at"),
            }
        )
    return out


def main():
    if not TOKEN or not COMPANY_ID:
        sys.exit(
            "Set PROCORE_ACCESS_TOKEN and PROCORE_COMPANY_ID environment variables.\n"
            "See the module docstring for setup."
        )

    projects = fetch_projects()
    print(f"Found {len(projects)} active projects", file=sys.stderr)

    for proj in projects:
        insps = fetch_inspections(proj["id"])
        for i in insps:
            i["category"] = classify(i)
        proj["inspections"] = insps
        proj["inspection_coverage"] = "full"
        print(f"  {proj['name']}: {len(insps)} inspections", file=sys.stderr)

    data = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source": "procore-api",
        "source_note": "Full inspection history pulled from the Procore REST API.",
        "company": {"id": int(COMPANY_ID), "name": os.environ.get("PROCORE_COMPANY_NAME", "")},
        "classification": {"fai_keywords": FAI_KEYWORDS, "quality_keywords": QUALITY_KEYWORDS},
        "projects": projects,
    }
    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data.json")
    with open(out_path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"Wrote {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
