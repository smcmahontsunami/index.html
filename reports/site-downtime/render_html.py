"""Fill template.html with week data (+ optional read-out) -> a single self-contained page.

Usage: python3 render_html.py data.json insights.json|- out.html
"""
import json, os, sys

here = os.path.dirname(os.path.abspath(__file__))
data = json.load(open(sys.argv[1]))
insights = json.load(open(sys.argv[2])) if sys.argv[2] != "-" else None
safe = lambda o: json.dumps(o, ensure_ascii=False).replace("</", "<\\/")
html = open(os.path.join(here, "template.html")).read()
html = html.replace("/*DATA*/null", safe(data)).replace("/*INSIGHTS*/null", safe(insights))
open(sys.argv[3], "w").write(html)
print(sys.argv[3], len(html) // 1024, "KB")
