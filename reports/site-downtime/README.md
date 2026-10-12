# Weekly site downtime report

Builds the Monday site-downtime read-out for the previous Sunday–Saturday (Central time) from MaintainX: every site-down event by location, reason and time, rolled up by district and company, with a six-week trend.

Outputs:
- **Web page** (Claude artifact "Site Downtime Weekly"), republished each Monday at the same link.
- **One PowerPoint slide** for the weekly surf deck: an editable .pptx, plus a copyable image at the top of the page.

No MaintainX data is stored in this repository. Each run pulls fresh from the API.

## Run

```bash
export MAINTAINX_API_KEY=...            # MaintainX REST API key
python3 build_week.py "" 6 data.json   # "" = last completed week; 6 weeks of history
# write insights.json for the latest week (format below)
npm install pptxgenjs@3.12.0            # once
node build_slide.js data.json insights.json Site_Downtime_<week>.pptx
soffice --headless --convert-to pdf Site_Downtime_<week>.pptx
pdftoppm -png -r 144 -singlefile Site_Downtime_<week>.pdf slide
python3 render_html.py data.json insights.json site_downtime.html slide.png   # slide image + copy button on the page
```

`insights.json`:

```json
{"week_start": "2026-10-04",
 "items": ["<strong>Lead.</strong> Detail for the web page read-out", "..."],
 "slide": {"title": "Slide headline with the week's key number",
           "bullets": [["Bold lead.", "One-line detail."], ["...", "..."]]}}
```

## Method

- An event is a work order in the **Site Down** category, or an **OFFLINE** status on a site-level asset.
- A status and a work order at the same site are joined when they overlap or start within 60 minutes of each other (or of the work order's completion).
- Down and up times come from the status when it lasts between 1 minute and 24 hours. Otherwise they come from the work order: `startDate` when it was logged after the fact, else created to completed.
- Statuses less than 5 minutes apart are merged.
- Events still open, or logged at 24 hours or more, are listed and flagged but left out of hour totals.
- Districts come from MaintainX teams named `District N [Manager]`, through each team's locations and assets.
- Reasons are classified by keyword (`CATEGORIES` in `build_week.py`).
- Times are elapsed clock time in Central time. They are not adjusted for operating hours or for sites in Eastern time.
