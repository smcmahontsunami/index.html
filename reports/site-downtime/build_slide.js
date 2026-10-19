// One 16:9 slide for the weekly surf deck, from build_week.py output + the week's read-out.
// Usage: node build_slide.js data.json insights.json out.pptx
// Hex colors (not theme colors) so the slide keeps its look when pasted into another deck.
const fs = require("fs");
const pptxgen = require("pptxgenjs");

const [dataPath, insPath, outPath] = process.argv.slice(2);
const DATA = JSON.parse(fs.readFileSync(dataPath, "utf8"));
const INS = JSON.parse(fs.readFileSync(insPath, "utf8"));
const W = DATA.weeks[DATA.weeks.length - 1];
const P = DATA.weeks.length > 1 ? DATA.weeks[DATA.weeks.length - 2] : null;
if (INS.week_start !== W.week_start) throw new Error(`Read-out is for ${INS.week_start}, data is ${W.week_start}`);

const NAVY = "0F2C55", GOLD = "C99A2E", INK = "1B2B44", MUTED = "5F6C80", LINE = "DCE3EC", TINT = "F3F6FA", WHITE = "FFFFFF";
const GOOD = "2F7D4F", BAD = "B23B2E", FONT = "Arial";
const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

const mins = w => w.events.filter(e => e.minutes != null).reduce((s, e) => s + e.minutes, 0);
const dur = m => (m >= 60 ? `${Math.floor(m / 60)}h ${String(m % 60).padStart(2, "0")}m` : `${m}m`);
const ymd = s => s.slice(0, 10).split("-").map(Number);
const range = w => { const [y, m, d] = ymd(w.week_start), [, m2, d2] = ymd(w.week_end);
  return m === m2 ? `${MON[m - 1]} ${d}–${d2}, ${y}` : `${MON[m - 1]} ${d} – ${MON[m2 - 1]} ${d2}, ${y}`; };
const sites = w => new Set(w.events.map(e => e.code)).size;
const open = w => w.events.filter(e => e.minutes == null).length;
const hist = DATA.weeks.slice(0, -1).map(mins);
const avg = hist.length ? hist.reduce((a, b) => a + b, 0) / hist.length : null;

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE"; // 13.33 x 7.5 in
pres.title = `Site downtime ${range(W)}`;
const s = pres.addSlide();
s.background = { color: WHITE };

// Header block in the surf-deck style: navy band, gold eyebrow.
s.addShape(pres.shapes.RECTANGLE, { x: 0, y: 0, w: 13.333, h: 1.32, fill: { color: NAVY }, line: { color: NAVY }, objectName: "Header" });
s.addText(`SITE DOWNTIME · WEEKLY · ${range(W).toUpperCase()} (SUN–SAT, CENTRAL TIME)`, {
  x: 0.5, y: 0.2, w: 12.3, h: 0.3, fontFace: FONT, fontSize: 12, bold: true, color: GOLD, charSpacing: 1.5, margin: 0, isTextBox: true, objectName: "Eyebrow" });
s.addText(INS.slide.title, { x: 0.5, y: 0.52, w: 12.3, h: 0.62, fontFace: FONT, fontSize: 26, bold: true, color: WHITE, margin: 0, valign: "middle", isTextBox: true, objectName: "Title" });

// KPI tiles.
const cmp = (cur, prev, f) => { if (prev == null) return [{ text: "" }]; const d = cur - prev;
  return d === 0 ? [{ text: "Same as prior week", options: { color: MUTED } }]
    : [{ text: `${d < 0 ? "▼" : "▲"} ${f(Math.abs(d))} `, options: { color: d < 0 ? GOOD : BAD, bold: true } },
       { text: `vs prior week (${f(prev)})`, options: { color: MUTED } }]; };
const kpis = [
  ["DOWN TIME, 7AM–8PM", dur(mins(W)), avg != null && P
    ? [...cmp(mins(W), mins(P), dur).slice(0, 1), { text: `vs prior wk · ${hist.length}-wk avg ${Math.round(avg / 60)}h`, options: { color: MUTED } }]
    : cmp(mins(W), P && mins(P), dur)],
  ["SITE-DOWN EVENTS", String(W.events.length), cmp(W.events.length, P && P.events.length, String)],
  ["SITES AFFECTED", `${sites(W)} of ${DATA.site_count}`, cmp(sites(W), P && sites(P), String)],
  ["OPEN / UNVERIFIED", String(open(W)), [{ text: open(W) ? "Excluded from hours until closed" : "All events have verified times", options: { color: MUTED } }]],
];
const kx = 0.5, kw = 2.92, kg = 0.2, ky = 1.55, kh = 1.05;
kpis.forEach(([lab, val, sub], i) => {
  const x = kx + i * (kw + kg);
  s.addShape(pres.shapes.RECTANGLE, { x, y: ky, w: kw, h: kh, fill: { color: TINT }, line: { color: LINE, width: 0.75 }, objectName: `KPI ${i + 1}` });
  s.addText(lab, { x: x + 0.18, y: ky + 0.1, w: kw - 0.3, h: 0.22, fontFace: FONT, fontSize: 10, bold: true, color: MUTED, charSpacing: 1, margin: 0, isTextBox: true });
  s.addText(val, { x: x + 0.18, y: ky + 0.32, w: kw - 0.3, h: 0.45, fontFace: FONT, fontSize: 26, bold: true, color: INK, margin: 0, valign: "middle", isTextBox: true });
  s.addText(sub.map(r => ({ text: r.text, options: { fontFace: FONT, fontSize: 10, ...(r.options || {}) } })),
    { x: x + 0.18, y: ky + 0.78, w: kw - 0.3, h: 0.22, margin: 0, isTextBox: true });
});

// Hours by district and by reason: native bar charts.
const group = key => { const g = {}; W.events.forEach(e => { g[e[key]] ??= { m: 0, n: 0 }; g[e[key]].n++; if (e.minutes != null) g[e[key]].m += e.minutes; }); return g; };
const dist = group("district"), cat = group("category");
const dnames = Object.keys(DATA.managers).sort((a, b) => parseInt(a.split(" ")[1]) - parseInt(b.split(" ")[1]));
const last = n => (n || "").trim().split(/\s+/).slice(-1)[0];
const dRows = dnames.map(d => ({ label: `D${d.split(" ")[1]}${DATA.managers[d] ? ` · ${last(DATA.managers[d])}` : ""}`, h: +((dist[d]?.m || 0) / 60).toFixed(1) }))
  .sort((a, b) => b.h - a.h);
const cRows = Object.entries(cat).map(([c, v]) => ({ label: c, h: +(v.m / 60).toFixed(1) })).sort((a, b) => b.h - a.h);

const cy = 2.85, ch = 3.95;
const chartOpts = (title, x, w, n) => ({
  x, y: cy, w, h: ch, barDir: "bar", chartColors: [NAVY], barGapWidthPct: 45,
  showTitle: true, title, titleFontFace: FONT, titleFontSize: 13, titleColor: INK, titleAlign: "left",
  catAxisLabelFontFace: FONT, catAxisLabelFontSize: n > 8 ? 10 : 11, catAxisLabelColor: INK, catAxisOrientation: "maxMin",
  valAxisHidden: true, valGridLine: { style: "none" }, catGridLine: { style: "none" }, catAxisLineShow: false,
  showValue: true, dataLabelPosition: "outEnd", dataLabelFormatCode: '0.0"h"', dataLabelFontFace: FONT, dataLabelFontSize: 10, dataLabelColor: INK,
  showLegend: false,
});
s.addChart(pres.charts.BAR, [{ name: "Hours", labels: dRows.map(r => r.label), values: dRows.map(r => r.h) }],
  { ...chartOpts("Down hours by district", 0.4, 4.25, dRows.length), objectName: "Chart: hours by district" });
s.addChart(pres.charts.BAR, [{ name: "Hours", labels: cRows.map(r => r.label), values: cRows.map(r => r.h) }],
  { ...chartOpts("Down hours by reason", 4.75, 4.0, cRows.length), objectName: "Chart: hours by reason" });

// Takeaways.
const tx = 9.0, tw = 3.85;
s.addText("WHAT TO ACT ON", { x: tx, y: cy + 0.05, w: tw, h: 0.28, fontFace: FONT, fontSize: 12, bold: true, color: NAVY, charSpacing: 1, margin: 0, isTextBox: true });
const runs = [];
INS.slide.bullets.forEach(([lead, rest], i) => {
  runs.push({ text: lead + " ", options: { bold: true, color: INK, bullet: { indent: 14 }, paraSpaceAfter: 7 } });
  runs.push({ text: rest, options: { color: INK, breakLine: i < INS.slide.bullets.length - 1 } });
});
s.addText(runs, { x: tx, y: cy + 0.4, w: tw, h: ch - 0.45, fontFace: FONT, fontSize: 12, valign: "top", margin: 0, isTextBox: true, objectName: "Takeaways" });

// Footer.
const pl = (n, w) => `${n} ${w}${n === 1 ? "" : "s"}`;
const unassigned = dist.Unassigned ? ` ${pl(dist.Unassigned.n, "event")} at sites with no district team ${dist.Unassigned.n === 1 ? "is" : "are"} left off the district chart.` : "";
const overnight = W.events.filter(e => e.overnight).length;
const on = overnight ? ` ${pl(overnight, "event")} ran overnight; hours outside 7am–8pm are not counted.` : " Hours outside 7am–8pm are not counted.";
s.addText(`Source: MaintainX Site Down work orders and site offline status. Hours count only events with verified down and up times (${pl(open(W), "open event")} excluded).${unassigned}${on} Central time.`,
  { x: 0.5, y: 6.95, w: 12.3, h: 0.35, fontFace: FONT, fontSize: 9, color: MUTED, margin: 0, valign: "middle", isTextBox: true, objectName: "Source" });

s.addNotes(INS.items.map(t => t.replace(/<[^>]+>/g, "")).join("\n\n"));
pres.writeFile({ fileName: outPath }).then(f => console.log(f));
