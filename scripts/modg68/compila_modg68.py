"""Compila il modulo Fornaca MO.DG.68 dal template, senza Word.
Uso:
  venv/bin/python scripts/modg68/compila_modg68.py dati.json uscita.pdf
dati.json:
{"paziente": "Rossi Mario", "cartella": "2026 0000", "assicurazione": "ASSICURAZIONE",
 "codici": ["1000 - 2000", "3000 al 50% - 4000 al 50%"], "totale": "1600,00",
 "equipe": [["Dr. G. Vasario", "1000,00"], ["Dr. A. Aiuto", "300,00"], ["Dr. B. Anestesista", "200,00"], ["Dr.ssa C. Strumentista", "100,00"]],
 "data": "01.01.2026"}
(dati di esempio inventati: il repository è pubblico)
Massimo 6 righe d'équipe, tutte con casella LP barrata (intra moenia mai usata finora)."""
import sys, json, pathlib, pymupdf
B = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
tpl = pathlib.Path(__file__).with_name("template.pdf")
k = json.load(open(sys.argv[1])); out = sys.argv[2]
d = pymupdf.open(tpl); p = d[0]
def w(x, y, s, size): p.insert_text((x, y), s, fontname="arialbd", fontfile=B, fontsize=size)
w(113.0, 148.7, k["paziente"], 12)
w(140.0, 175.5, k["cartella"], 10.1)
w(123.8, 198.6, k["assicurazione"], 12)
if k.get("codici"):
    w(227.8, 162.0, f"[ da tariffario {k['assicurazione']} ]:", 7.9)
    for i, c in enumerate(k["codici"][:2]): w(227.8, 175.8 + 14 * i, c, 7.9)
w(214.0, 295.4, k["totale"], 10.1)
eq = k["equipe"]; assert 1 <= len(eq) <= 6, "da 1 a 6 righe"
ROW = [345.4, 380.2, 415.2, 450.0, 485.4, 522.8]          # y della casella LP di ogni riga
for i, y in enumerate(ROW):
    for dy in (0, 17.7):                                    # caselle LP e INTRA MOENIA
        r = pymupdf.Rect(332.2, y + 4.4 + dy, 339.6, y + 11.8 + dy); p.draw_rect(r, width=0.7)
        if i < len(eq) and dy == 0:
            p.draw_line(r.tl, r.br, width=0.7); p.draw_line(r.tr, r.bl, width=0.7)
for i, (nome, quota) in enumerate(eq):
    w(69.1, ROW[i] + 20.5, nome, 11); w(459.0, ROW[i] + 25.0, quota, 10.6)
w(86.9, 790.0, k["data"], 12)
d.subset_fonts(); d.save(out, garbage=4, deflate=True)
# controllo: la somma delle quote deve dare il totale
n = lambda s: float(s.replace(".", "").replace(",", "."))
tot = round(sum(n(q) for _, q in eq), 2)
print("ok", out, "| somma quote", tot, "| totale", n(k["totale"]), "| OK" if abs(tot - n(k["totale"])) < 0.005 else "| ⚠️ NON TORNA")
