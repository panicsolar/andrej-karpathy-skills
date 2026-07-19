#!/usr/bin/env python3
"""Render data.json into a self-contained dashboard.html.

    python3 render.py            # reads data.json, writes dashboard.html

No third-party dependencies. The output HTML inlines all CSS/JS so it can be
opened directly in a browser or published as an artifact.
"""

import html
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
FAI_KEYWORDS = ["fai", "first article"]
QUALITY_KEYWORDS = ["quality", "qa/qc", "qaqc", "qc "]

STATUS_CLASS = {
    "open": "st-open",
    "in review": "st-review",
    "closed": "st-closed",
    "not started": "st-open",
}


def classify(insp):
    haystack = " ".join(
        str(insp.get(k) or "") for k in ("name", "template_name", "type")
    ).lower()
    if any(k in haystack for k in FAI_KEYWORDS):
        return "fai"
    if any(k in haystack for k in QUALITY_KEYWORDS):
        return "quality"
    return "other"


def esc(v):
    return html.escape(str(v)) if v is not None else "—"


def status_pill(status):
    cls = STATUS_CLASS.get(str(status or "").lower(), "st-other")
    return f'<span class="pill {cls}">{esc(status or "—")}</span>'


def cat_badge(cat):
    label = {"fai": "FAI", "quality": "Quality", "other": "Other"}[cat]
    return f'<span class="cat cat-{cat}">{label}</span>'


def inspection_rows(items, project_name):
    rows = []
    for i in items:
        cat = i.get("category") or classify(i)
        rows.append(
            "<tr>"
            f'<td class="c-proj">{esc(project_name)}</td>'
            f'<td>{esc(i.get("name"))}</td>'
            f'<td>{esc(i.get("type"))}</td>'
            f"<td>{cat_badge(cat)}</td>"
            f"<td>{status_pill(i.get('status'))}</td>"
            f'<td class="c-date">{esc(i.get("inspection_date") or (i.get("created_date") or "")[:10])}</td>'
            "</tr>"
        )
    return rows


def build(data):
    company = data.get("company", {})
    projects = data.get("projects", [])
    source = data.get("source", "")
    generated = data.get("generated_at", "")
    is_snapshot = source == "zapier-snapshot"

    # Flatten + classify.
    all_insp = []
    for p in projects:
        for i in p.get("inspections", []):
            i = dict(i)
            i["category"] = i.get("category") or classify(i)
            i["_project"] = p.get("name", "")
            all_insp.append(i)

    quality = [i for i in all_insp if i["category"] == "quality"]
    fais = [i for i in all_insp if i["category"] == "fai"]

    def open_count(items):
        return sum(1 for i in items if str(i.get("status", "")).lower() != "closed")

    projects_with_data = [p for p in projects if p.get("inspections")]

    kpis = [
        ("Active projects", len(projects), ""),
        ("Projects w/ inspection data", len(projects_with_data), f"of {len(projects)}"),
        ("Quality inspections", len(quality), f"{open_count(quality)} open"),
        ("FAIs", len(fais), f"{open_count(fais)} open"),
        ("Total inspections pulled", len(all_insp), ""),
    ]
    kpi_html = "".join(
        f'<div class="kpi"><div class="kpi-v">{v}</div><div class="kpi-l">{esc(l)}</div>'
        f'<div class="kpi-s">{esc(s)}</div></div>'
        for l, v, s in kpis
    )

    def table(items, empty_msg):
        if not items:
            return f'<p class="empty">{esc(empty_msg)}</p>'
        rows = []
        for i in items:
            rows.append(inspection_rows([i], i.get("_project", ""))[0])
        return (
            '<table><thead><tr><th>Project</th><th>Inspection</th><th>Type</th>'
            "<th>Category</th><th>Status</th><th>Date</th></tr></thead><tbody>"
            + "".join(rows)
            + "</tbody></table>"
        )

    # Overview: one row per project with its latest inspection.
    ov_rows = []
    for p in sorted(projects, key=lambda x: x.get("name", "")):
        insps = p.get("inspections", [])
        if insps:
            latest = max(insps, key=lambda i: (i.get("inspection_date") or i.get("created_date") or ""))
            q = sum(1 for i in insps if (i.get("category") or classify(i)) == "quality")
            f = sum(1 for i in insps if (i.get("category") or classify(i)) == "fai")
            ov_rows.append(
                "<tr>"
                f'<td class="c-proj">{esc(p.get("name"))}</td>'
                f'<td>{esc(latest.get("name"))}</td>'
                f'<td>{esc(latest.get("type"))}</td>'
                f"<td>{status_pill(latest.get('status'))}</td>"
                f'<td class="c-date">{esc(latest.get("inspection_date") or (latest.get("created_date") or "")[:10])}</td>'
                f'<td class="c-num">{q}</td><td class="c-num">{f}</td>'
                "</tr>"
            )
        else:
            ov_rows.append(
                "<tr class=\"no-data\">"
                f'<td class="c-proj">{esc(p.get("name"))}</td>'
                '<td colspan="4" class="empty-cell">no inspection data pulled</td>'
                '<td class="c-num">—</td><td class="c-num">—</td>'
                "</tr>"
            )
    overview_table = (
        '<table><thead><tr><th>Project</th><th>Latest inspection</th><th>Type</th>'
        "<th>Status</th><th>Date</th><th>Quality</th><th>FAI</th></tr></thead><tbody>"
        + "".join(ov_rows)
        + "</tbody></table>"
    )

    banner = ""
    if is_snapshot:
        banner = (
            '<div class="banner">'
            "<strong>Snapshot — limited coverage.</strong> This data came from the Procore "
            "connection via Zapier, which only returns the <em>single most-recent</em> inspection "
            "per project. Quality inspections and FAIs older than a project&rsquo;s latest Safety "
            "check are not reachable this way, so those tabs may be empty. For full history and "
            "reliable Quality/FAI separation, run <code>fetch_procore.py</code> with a Procore API "
            "token, then re-run <code>render.py</code>."
            "</div>"
        )

    title = f"Quality Inspections &amp; FAIs — {esc(company.get('name', 'Procore'))}"
    return TEMPLATE.format(
        title=title,
        company=esc(company.get("name", "")),
        generated=esc(generated),
        source=esc(source),
        banner=banner,
        kpis=kpi_html,
        overview=overview_table,
        quality=table(quality, "No Quality inspections in the pulled data. If you expected some, "
                               "the snapshot's latest-only limit is likely hiding them — run the API fetcher."),
        fai=table(fais, "No FAIs in the pulled data. If you expected some, the snapshot's "
                         "latest-only limit is likely hiding them — run the API fetcher."),
        allinsp=table(all_insp, "No inspections pulled."),
    )


TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
  :root {{
    --bg:#f6f7f9; --card:#fff; --ink:#1a1f26; --muted:#5b6572; --line:#e3e7ec;
    --accent:#2f6bff; --quality:#0d8a5f; --fai:#b4531a; --other:#7a8290;
    --open:#b4531a; --review:#8a6d0d; --closed:#0d8a5f;
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{
      --bg:#0f1319; --card:#161c24; --ink:#e7ecf2; --muted:#9aa5b2; --line:#26303c;
      --accent:#5c8bff; --quality:#37c48a; --fai:#e0894f; --other:#8a94a2;
      --open:#e0894f; --review:#e0c04f; --closed:#37c48a;
    }}
  }}
  :root[data-theme="dark"] {{
    --bg:#0f1319; --card:#161c24; --ink:#e7ecf2; --muted:#9aa5b2; --line:#26303c;
    --accent:#5c8bff; --quality:#37c48a; --fai:#e0894f; --other:#8a94a2;
    --open:#e0894f; --review:#e0c04f; --closed:#37c48a;
  }}
  :root[data-theme="light"] {{
    --bg:#f6f7f9; --card:#fff; --ink:#1a1f26; --muted:#5b6572; --line:#e3e7ec;
    --accent:#2f6bff; --quality:#0d8a5f; --fai:#b4531a; --other:#7a8290;
    --open:#b4531a; --review:#8a6d0d; --closed:#0d8a5f;
  }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--ink);
    font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif; }}
  .wrap {{ max-width:1180px; margin:0 auto; padding:28px 20px 60px; }}
  header {{ display:flex; flex-wrap:wrap; align-items:baseline; gap:8px 16px; margin-bottom:6px; }}
  h1 {{ font-size:22px; margin:0; letter-spacing:-.01em; }}
  .meta {{ color:var(--muted); font-size:13px; }}
  .banner {{ background:color-mix(in srgb, var(--fai) 12%, var(--card));
    border:1px solid color-mix(in srgb, var(--fai) 40%, var(--line));
    border-radius:10px; padding:12px 14px; margin:16px 0 22px; font-size:13.5px; color:var(--ink); }}
  .banner code {{ background:color-mix(in srgb,var(--ink) 10%,transparent); padding:1px 5px; border-radius:4px; font-size:12px; }}
  .kpis {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr)); gap:12px; margin:18px 0 26px; }}
  .kpi {{ background:var(--card); border:1px solid var(--line); border-radius:12px; padding:14px 16px; }}
  .kpi-v {{ font-size:28px; font-weight:650; letter-spacing:-.02em; }}
  .kpi-l {{ font-size:12.5px; color:var(--muted); margin-top:2px; }}
  .kpi-s {{ font-size:12px; color:var(--muted); margin-top:4px; min-height:15px; }}
  .tabs {{ display:flex; flex-wrap:wrap; gap:4px; border-bottom:1px solid var(--line); margin-bottom:2px; }}
  .tab {{ appearance:none; border:0; background:transparent; color:var(--muted); cursor:pointer;
    padding:9px 14px; font-size:14px; font-weight:550; border-bottom:2px solid transparent; }}
  .tab:hover {{ color:var(--ink); }}
  .tab.active {{ color:var(--accent); border-bottom-color:var(--accent); }}
  .panel {{ display:none; padding-top:16px; }}
  .panel.active {{ display:block; }}
  .tablewrap {{ overflow-x:auto; border:1px solid var(--line); border-radius:12px; background:var(--card); }}
  table {{ width:100%; border-collapse:collapse; font-size:13.5px; min-width:640px; }}
  th, td {{ text-align:left; padding:10px 14px; border-bottom:1px solid var(--line); vertical-align:top; }}
  th {{ font-size:11.5px; text-transform:uppercase; letter-spacing:.04em; color:var(--muted); font-weight:600; position:sticky; top:0; background:var(--card); }}
  tr:last-child td {{ border-bottom:0; }}
  .c-proj {{ font-weight:600; white-space:nowrap; }}
  .c-date {{ white-space:nowrap; color:var(--muted); }}
  .c-num {{ text-align:center; color:var(--muted); }}
  tr.no-data td {{ color:var(--muted); }}
  .empty-cell {{ color:var(--muted); font-style:italic; }}
  .empty {{ color:var(--muted); padding:22px 6px; font-style:italic; }}
  .pill {{ display:inline-block; padding:2px 9px; border-radius:20px; font-size:12px; font-weight:600;
    border:1px solid currentColor; white-space:nowrap; }}
  .st-open {{ color:var(--open); }} .st-review {{ color:var(--review); }}
  .st-closed {{ color:var(--closed); }} .st-other {{ color:var(--other); }}
  .cat {{ display:inline-block; padding:2px 8px; border-radius:6px; font-size:11.5px; font-weight:700; }}
  .cat-quality {{ background:color-mix(in srgb,var(--quality) 18%,transparent); color:var(--quality); }}
  .cat-fai {{ background:color-mix(in srgb,var(--fai) 18%,transparent); color:var(--fai); }}
  .cat-other {{ background:color-mix(in srgb,var(--other) 16%,transparent); color:var(--other); }}
  footer {{ margin-top:28px; color:var(--muted); font-size:12px; }}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>Quality Inspections &amp; FAIs</h1>
    <span class="meta">{company} &middot; generated {generated} &middot; source: {source}</span>
  </header>
  {banner}
  <div class="kpis">{kpis}</div>
  <div class="tabs" role="tablist">
    <button class="tab active" data-t="overview">Overview</button>
    <button class="tab" data-t="quality">Quality Inspections</button>
    <button class="tab" data-t="fai">FAIs</button>
    <button class="tab" data-t="allinsp">All Inspections</button>
  </div>
  <section class="panel active" id="overview"><div class="tablewrap">{overview}</div></section>
  <section class="panel" id="quality">{quality}</section>
  <section class="panel" id="fai">{fai}</section>
  <section class="panel" id="allinsp">{allinsp}</section>
  <footer>Procore Quality Dashboard &middot; static snapshot. Re-run <code>fetch_procore.py</code> then <code>render.py</code> to refresh.</footer>
</div>
<script>
  document.querySelectorAll('.tab').forEach(function(t) {{
    t.addEventListener('click', function() {{
      document.querySelectorAll('.tab').forEach(function(x) {{ x.classList.remove('active'); }});
      document.querySelectorAll('.panel').forEach(function(x) {{ x.classList.remove('active'); }});
      t.classList.add('active');
      document.getElementById(t.dataset.t).classList.add('active');
    }});
  }});
</script>
</body>
</html>
"""


def main():
    with open(os.path.join(HERE, "data.json")) as f:
        data = json.load(f)
    out = build(data)
    out_path = os.path.join(HERE, "dashboard.html")
    with open(out_path, "w") as f:
        f.write(out)
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
