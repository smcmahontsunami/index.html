"""Fill template.html with week data (+ optional read-out) -> a single self-contained page.

Usage: python3 render_html.py data.json insights.json|- out.html [slide.png]
slide.png = the rendered surf-deck slide, shown on the page with a copy button.
"""
import base64, json, os, sys

here = os.path.dirname(os.path.abspath(__file__))
data = json.load(open(sys.argv[1]))
insights = json.load(open(sys.argv[2])) if sys.argv[2] != "-" else None
safe = lambda o: json.dumps(o, ensure_ascii=False).replace("</", "<\\/")
html = open(os.path.join(here, "template.html")).read()
slide = None
if len(sys.argv) > 4:
    png = base64.b64encode(open(sys.argv[4], "rb").read()).decode()
    slide = {"week_start": data["weeks"][-1]["week_start"], "png": "data:image/png;base64," + png}
html = html.replace("/*DATA*/null", safe(data)).replace("/*INSIGHTS*/null", safe(insights))
html = html.replace("/*SLIDE*/null", safe(slide))
open(sys.argv[3], "w").write(html)
print(sys.argv[3], len(html) // 1024, "KB")
