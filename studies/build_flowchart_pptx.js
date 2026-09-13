const pptxgen = require("pptxgenjs");
const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE";
const NAVY="16263F", TEAL="1A8FA0", AMBER="C87F16", GREEN="2E9E63", GREY="6C7891", SLATE="37415A", LIGHT="EEF1F5", WHITE="FFFFFF", RED="B23B3B", INK="2A3446";
const s = pres.addSlide(); s.background = { color: WHITE };
const F = "Calibri";
function box(x, y, w, h, title, sub, fill) {
  s.addText([{ text: title, options: { bold: true, fontSize: 12, color: WHITE, breakLine: true } },
             { text: sub, options: { fontSize: 9, color: WHITE } }],
    { x, y, w, h, shape: pres.ShapeType.roundRect, rectRadius: 0.12, fill: { color: fill },
      line: { color: fill, width: 0.5 }, align: "center", valign: "middle", fontFace: F, margin: 6, isTextBox: true, paraSpaceAfter: 2 });
}
function line(x, y, w, h, o = {}) {
  const opt = { x, y, w, h, line: { color: o.color || GREY, width: o.width || 1.75 } };
  if (o.end) opt.line.endArrowType = "triangle"; if (o.begin) opt.line.beginArrowType = "triangle";
  if (o.dash) opt.line.dashType = "dash"; if (o.flipH) opt.flipH = true; if (o.flipV) opt.flipV = true;
  s.addShape(pres.ShapeType.line, opt);
}
function txt(x, y, w, h, t, o = {}) {
  s.addText(t, { x, y, w, h, fontSize: o.size || 8, color: o.color || GREY, fontFace: F, italic: !!o.italic,
    bold: !!o.bold, align: o.align || "center", valign: o.valign || "top", margin: 0, isTextBox: true });
}
const ink = (x, y, w, h, o = {}) => line(x, y, w, h, { color: INK, width: 1.25, ...o });
const dot = (x, y, r, c) => s.addShape(pres.ShapeType.ellipse, { x: x - r, y: y - r, w: 2*r, h: 2*r, fill: { color: c || RED }, line: { color: c || RED, width: 0.3 } });
const rect = (x, y, w, h, c, fill) => s.addShape(pres.ShapeType.rect, { x, y, w, h, fill: fill ? { color: fill } : { color: WHITE, transparency: 100 }, line: { color: c || INK, width: 1.1 } });

// ------------------------------------------------------------------ title
s.addText("Structural Optimization Studio — system flowchart with examples", { x: 0.6, y: 0.12, w: 10, h: 0.4,
  fontSize: 16, bold: true, color: NAVY, fontFace: F, margin: 0, isTextBox: true });

// ------------------------------------------------------------------ GA loop group
s.addShape(pres.ShapeType.roundRect, { x: 5.25, y: 0.62, w: 4.95, h: 4.95, rectRadius: 0.15,
  fill: { color: LIGHT, transparency: 60 }, line: { color: AMBER, width: 1, dashType: "dash" } });
txt(7.4, 5.28, 2.7, 0.25, "Genetic-algorithm loop", { size: 9.5, italic: true, color: AMBER, align: "right" });

// ------------------------------------------------------------------ rows
const W = 2.1, H = 1.0;
box(0.6, 0.75, W, H, "1. Problem library", "15 formulations: steel, frequency,\nRC carbon, AISC ASD / LRFD", NAVY);
box(3.05, 0.75, W, H, "2. User inputs", "loads, span, bracing, Fy, Cb,\nmaterial route, GA budget", SLATE);
box(5.5, 0.75, W, H, "3. Initialize GA", "normalized genotype [0,1]^n\nseeded population", AMBER);
line(2.7, 1.25, 0.35, 0, { end: true }); line(5.15, 1.25, 0.35, 0, { end: true });
box(0.6, 2.3, W, H, "8. Verification", "43 tests: closed forms, published\ndesigns, code paths, suite smoke", GREEN);
box(5.5, 2.3, W, H, "4. Evaluate design", "FE / modal / RC strain-compat. /\nAISC F2–F5, G2", TEAL);
box(7.95, 2.3, W, H, "5. Fitness map", "feasible: objective; else penalty\n(violation count or freq-error)", TEAL);
line(6.55, 1.75, 0, 0.55, { end: true }); line(7.6, 2.8, 0.35, 0, { end: true });
line(2.7, 2.8, 2.8, 0, { end: true, dash: true, color: GREEN }); txt(3.0, 2.5, 2.2, 0.25, "pins the mechanics", { italic: true, color: GREEN, size: 9 });
s.addText([{ text: "converged /\nbudget?", options: { fontSize: 10, color: NAVY, bold: true } }],
  { x: 8.05, y: 3.95, w: 1.9, h: 1.3, shape: pres.ShapeType.diamond, fill: { color: LIGHT }, line: { color: GREY, width: 1 },
    align: "center", valign: "middle", fontFace: F, margin: 2, isTextBox: true });
line(9.0, 3.3, 0, 0.65, { end: true });
box(5.5, 4.1, W, H, "6. Reproduce", "tournament · blend crossover ·\nadaptive mutation · elitism", AMBER);
line(7.6, 4.6, 0.45, 0, { begin: true, color: AMBER }); txt(7.55, 4.25, 0.55, 0.25, "no", { italic: true, color: AMBER, size: 9 });
line(6.55, 3.3, 0, 0.8, { begin: true, color: AMBER });
box(10.5, 4.1, W, H, "7. Post-process", "polish · details · 3-D model ·\ncarbon total + breakdown", NAVY);
line(9.95, 4.6, 0.55, 0, { end: true, color: GREEN }); txt(9.95, 4.25, 0.55, 0.25, "yes", { italic: true, color: GREEN, size: 9 });
box(0.6, 5.85, 9.5, 1.0, "9. Outputs", "live convergence charts · constraint-utilisation tables · section properties · embodied-carbon report · JSON export · PDF documentation · reproducibility studies", SLATE);
line(11.55, 5.1, 0, 0.4); line(9.5, 5.5, 2.05, 0); line(9.5, 5.5, 0, 0.35, { end: true });

// ------------------------------------------------------------------ example: input chips under block 2
[["M = 100 kN·m", 3.05, 0.8], ["L = 7 m", 3.9, 0.5], ["Lb = L · Cb 1", 4.45, 0.7]].forEach(([t, x, w]) =>
  s.addText(t, { x, y: 1.86, w, h: 0.26, shape: pres.ShapeType.roundRect, rectRadius: 0.13,
    fill: { color: LIGHT }, line: { color: GREY, width: 0.5 }, fontSize: 7, color: INK, fontFace: F, align: "center", valign: "middle", margin: 1, isTextBox: true }));
// genotype chips under block 3 (either side of the arrow)
["0.42", "0.18", "0.77"].forEach((v, i) => s.addText(v, { x: 5.5 + i*0.32, y: 1.86, w: 0.3, h: 0.24, shape: pres.ShapeType.rect,
  fill: { color: AMBER, transparency: 55 }, line: { color: AMBER, width: 0.5 }, fontSize: 6.5, color: INK, fontFace: F, align: "center", valign: "middle", margin: 0, isTextBox: true }));
["0.55", "0.09", "0.31"].forEach((v, i) => s.addText(v, { x: 6.68 + i*0.32, y: 1.86, w: 0.3, h: 0.24, shape: pres.ShapeType.rect,
  fill: { color: AMBER, transparency: 55 }, line: { color: AMBER, width: 0.5 }, fontSize: 6.5, color: INK, fontFace: F, align: "center", valign: "middle", margin: 0, isTextBox: true }));
// fitness formula beside the 5 -> decision arrow
txt(9.15, 3.38, 1.0, 0.5, "F = m(x)  if feasible\nelse P + w·v(x) + m(x)", { size: 7, italic: true, color: INK, align: "left" });
// crossover pictogram under block 6
const sq = (x, y, c) => s.addShape(pres.ShapeType.rect, { x, y, w: 0.13, h: 0.13, fill: { color: c }, line: { color: c, width: 0.3 } });
[TEAL, TEAL, TEAL].forEach((c, i) => sq(5.55 + i*0.15, 5.22, c)); [AMBER, AMBER, AMBER].forEach((c, i) => sq(6.15 + i*0.15, 5.22, c));
line(6.62, 5.285, 0.25, 0, { end: true, width: 1 }); [TEAL, AMBER, TEAL].forEach((c, i) => sq(6.92 + i*0.15, 5.22, c));
txt(5.5, 5.37, 2.0, 0.2, "crossover: parents → child", { size: 7, italic: true, align: "left" });
// verification checks under block 8
["closed-form anchors", "published designs", "code classifications"].forEach((t, i) => {
  txt(0.7, 3.43 + i*0.19, 1.9, 0.2, "✓ " + t, { size: 7.5, color: INK, align: "left" });
});

// ------------------------------------------------------------------ gallery: forms of the structures (block 1)
txt(0.6, 4.02, 4.5, 0.22, "Structure forms in the library (block 1)", { size: 8.5, bold: true, color: NAVY, align: "left" });
const gx = [0.62, 1.27, 1.92, 2.57, 3.22, 3.87, 4.52], gy = 4.32, cw = 0.55;
// 1 planar truss (two bays)
{ const x = gx[0], y = gy; const bx = [0, 0.27, 0.54], t = y, b = y + 0.42;
  ink(x, t, 0.54, 0); ink(x, b, 0.54, 0); bx.forEach(dx => ink(x + dx, t, 0, 0.42));
  ink(x, t, 0.27, 0.42); ink(x + 0.27, t, 0.27, 0.42); [t, b].forEach(yy => dot(x, yy, 0.025, INK)); }
// 2 tower (lattice: legs, rungs, zig-zag bracing)
{ const x = gx[1], y = gy; ink(x + 0.05, y, 0.15, 0.5, { flipV: true }); ink(x + 0.35, y, 0.15, 0.5);
  ink(x + 0.05, y + 0.5, 0.45, 0); ink(x + 0.2, y, 0.15, 0); ink(x + 0.10, y + 0.333, 0.35, 0); ink(x + 0.15, y + 0.167, 0.25, 0);
  ink(x + 0.05, y + 0.333, 0.40, 0.167, { flipV: true }); ink(x + 0.15, y + 0.167, 0.30, 0.166); ink(x + 0.15, y, 0.20, 0.167, { flipV: true }); }
// 3 frame (three storeys)
{ const x = gx[2], y = gy; [0, 0.27, 0.54].forEach(dx => ink(x + dx, y, 0, 0.52)); [0.16, 0.34, 0.52].forEach(dy => ink(x, y + dy, 0.54, 0));
  ink(x - 0.03, y + 0.52, 0.6, 0, { width: 1.8 }); }
// 4 RC beam section
{ const x = gx[3] + 0.08, y = gy; rect(x, y, 0.38, 0.52); rect(x + 0.05, y + 0.05, 0.28, 0.42, RED); [0.09, 0.19, 0.29].forEach(dx => dot(x + dx, y + 0.44, 0.03)); [0.11, 0.27].forEach(dx => dot(x + dx, y + 0.08, 0.02)); }
// 5 RC column section
{ const x = gx[4] + 0.08, y = gy + 0.03; rect(x, y, 0.38, 0.46); rect(x + 0.05, y + 0.05, 0.28, 0.36, RED); [[0.09, 0.09], [0.29, 0.09], [0.09, 0.37], [0.29, 0.37], [0.19, 0.09], [0.19, 0.37]].forEach(([a, b]) => dot(x + a, y + b, 0.028)); }
// 6 footing
{ const x = gx[5], y = gy; rect(x + 0.2, y, 0.15, 0.3); rect(x, y + 0.3, 0.55, 0.14); ink(x - 0.03, y + 0.22, 0.6, 0, { dash: true, width: 0.9 });
  [0.06, 0.16, 0.26, 0.36, 0.46].forEach(dx => dot(x + dx, y + 0.4, 0.022)); }
// 7 built-up I-beam
{ const x = gx[6] + 0.06, y = gy; rect(x, y, 0.42, 0.08, INK, INK); rect(x + 0.17, y + 0.08, 0.08, 0.36, INK, INK); rect(x, y + 0.44, 0.42, 0.08, INK, INK); }
["trusses", "towers", "frames", "RC beam", "RC column", "footing", "I-beam"].forEach((t, i) => txt(gx[i] - 0.06, 4.9, cw + 0.14, 0.22, t, { size: 7.5, color: INK }));
txt(0.6, 5.2, 4.5, 0.4, "weight / volume objectives for steel and aluminium; embodied CO₂ for reinforced concrete; AISC ASD and LRFD member design", { size: 7.5, italic: true, align: "left" });

// ------------------------------------------------------------------ right column: what block 4 evaluates
txt(10.5, 0.7, 2.4, 0.22, "What block 4 evaluates — examples", { size: 8.5, bold: true, color: NAVY, align: "left" });
// (i) FE frame with deflected shape and load
{ const x = 10.62, y = 1.0; ink(x, y + 0.1, 0, 0.55); ink(x + 0.7, y + 0.1, 0, 0.55); ink(x, y + 0.1, 0.7, 0); ink(x - 0.04, y + 0.65, 0.78, 0, { width: 1.8 });
  line(x + 0.05, y + 0.1, 0, 0.55, { color: TEAL, dash: true, width: 1 }); line(x + 0.75, y + 0.1, 0, 0.55, { color: TEAL, dash: true, width: 1 }); line(x + 0.05, y + 0.1, 0.7, 0, { color: TEAL, dash: true, width: 1 });
  line(x - 0.3, y + 0.1, 0.3, 0, { end: true, color: RED, width: 1.5 });
  txt(11.5, 1.05, 1.45, 0.6, "direct-stiffness FE:\nforces, drift, deflection\n(dashed = deformed)", { size: 7.5, color: INK, align: "left" }); }
// (ii) RC strain compatibility: section + strain triangle
{ const x = 10.62, y = 1.85; rect(x, y, 0.36, 0.55); [0.09, 0.27].forEach(dx => dot(x + dx, y + 0.48, 0.028)); [0.09, 0.27].forEach(dx => dot(x + dx, y + 0.07, 0.02));
  s.addShape(pres.ShapeType.rtTriangle, { x: x + 0.5, y: y, w: 0.3, h: 0.55, fill: { color: TEAL, transparency: 70 }, line: { color: TEAL, width: 0.8 }, flipH: true });
  txt(x + 0.86, y - 0.02, 0.5, 0.2, "εcu = 0.003", { size: 6.5, color: INK, align: "left" }); txt(x + 0.86, y + 0.38, 0.6, 0.2, "εt ≥ 0.004", { size: 6.5, color: INK, align: "left" });
  txt(11.5, 2.5, 1.45, 0.34, "strain compatibility: φMn, φ transition, doubly reinforced", { size: 7.5, color: INK, align: "left" }); }
// (iii) native P–M interaction chart (editable)
s.addChart(pres.ChartType.scatter, [
  { name: "X-Axis", values: [0, 60, 110, 150, 165, 150, 120] },
  { name: "φPn–φMn", values: [1750, 1700, 1500, 1100, 700, 300, 0] },
], { x: 10.5, y: 2.9, w: 2.45, h: 1.0, lineSize: 2, lineDataSymbol: "none", chartColors: [NAVY],
     showLegend: false, showTitle: true, title: "column P–M interaction", titleFontSize: 7, titleColor: NAVY,
     catAxisLabelFontSize: 6, valAxisLabelFontSize: 6, catAxisLabelColor: GREY, valAxisLabelColor: GREY,
     catAxisTitle: "φMn (kN·m)", showCatAxisTitle: true, catAxisTitleFontSize: 6, valAxisTitle: "φPn (kN)", showValAxisTitle: true, valAxisTitleFontSize: 6,
     valGridLine: { color: "E6E9EF", size: 0.5 }, catGridLine: { style: "none" } });

// ------------------------------------------------------------------ carbon doughnut beside Outputs (block 7/9 example)
s.addChart(pres.ChartType.doughnut, [{ name: "kg CO₂", labels: ["concrete", "steel", "formwork"], values: [286, 419, 27] }],
  { x: 10.35, y: 5.55, w: 2.5, h: 1.45, holeSize: 55, chartColors: [GREY, NAVY, AMBER], showPercent: true, dataLabelFontSize: 6.5, dataLabelColor: WHITE,
    showLegend: true, legendPos: "r", legendFontSize: 7, showTitle: true, title: "carbon breakdown — RC beam", titleFontSize: 7, titleColor: NAVY });

s.addNotes("System flowchart with worked examples: structure pictograms for the problem library, input chips, genotype cells, the fitness rule, a crossover pictogram, verification checks, FE/strain-compatibility/P–M examples for the evaluation step, and a carbon-breakdown chart. All objects are native and editable; the two charts are native PowerPoint charts.");
pres.writeFile({ fileName: "/home/claude/flow/System_Flowchart.pptx" }).then(() => console.log("written"));
