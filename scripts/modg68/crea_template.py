"""Crea il modulo MO.DG.68 vuoto (template.pdf) da un modulo già compilato.
Uso (una volta sola, o se Fornaca cambia il modulo):
  venv/bin/python scripts/modg68/crea_template.py "<MO.DG.68 compilato>.pdf"
Toglie i dati variabili e lascia grafica, logo, firma e testi fissi."""
import sys, pathlib, pymupdf
ARIAL = "/System/Library/Fonts/Supplemental/Arial.ttf"
out = pathlib.Path(__file__).with_name("template.pdf")
d = pymupdf.open(sys.argv[1]); p = d[0]
labels = []
for b in p.get_text("dict")["blocks"]:
    for l in b.get("lines", []):
        for s in l["spans"]:
            t = s["text"].strip(); r = pymupdf.Rect(s["bbox"]); bold = "Bold" in s["font"]
            if t == "Dr. G. Vasario" and r.y0 > 770: continue          # firma: resta
            var = (bold and s["size"] < 12.5 and t != "DIREZIONE GENERALE") or t in ("☒", "□") \
                  or t.startswith("Cartella numero") or t.startswith("€ ____")
            if not var: continue
            if bold and t not in ("☒", "□"): r.y1 = r.y0 + 2.5   # tocca solo il testo, non le righe ____ sotto
            p.add_redact_annot(r)
            if t.startswith("Cartella numero"): labels.append((r.x0, r.y1 - 2.3, "Cartella numero: ________________"))
            if t.startswith("€ ____"): labels.append((r.x0, r.y1 - 2.3, "€ ___________________________"))
p.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE, graphics=pymupdf.PDF_REDACT_LINE_ART_NONE)
for x, y, s in labels: p.insert_text((x, y), s, fontname="arial", fontfile=ARIAL, fontsize=10.1)
d.subset_fonts(); d.save(out, garbage=4, deflate=True); print("ok", out)
