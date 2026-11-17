"""Sola lettura: mostra P.IVA e codice fiscale SALVATI nell'intestatario dei documenti emessi.

Uso: venv/bin/python -I scripts/verifica_intestatario.py AAAA-MM [parte del nome cliente]
Esempio: venv/bin/python -I scripts/verifica_intestatario.py 2026-07 CELLINI

Perché: il 17/11/2026 FE155-159 risultarono emesse con la vecchia P.IVA di Cellini perché il
server tiene in cache 24 ore i dati del cliente. L'anagrafica giusta in FIC e la risposta di
create_invoice non provano nulla: conta il dato scritto nel documento.
Legge token e company id dalla configurazione MCP dell'app Claude (non li stampa).
"""
import calendar, json, os, sys
cfg = json.load(open(os.path.expanduser("~/Library/Application Support/Claude/claude_desktop_config.json")))
os.environ.update(cfg["mcpServers"]["fattureincloud"]["env"])
os.environ["FIC_CACHE_DISABLED"] = "1"
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import server

ym = sys.argv[1]
name = (sys.argv[2] if len(sys.argv) > 2 else "").upper()
y, m = map(int, ym.split("-"))
last = calendar.monthrange(y, m)[1]
for t in ("invoice", "credit_note"):
    page = 1
    while True:
        r = server.issued_api.list_issued_documents(
            company_id=server.COMPANY_ID, type=t,
            q=f"date >= '{ym}-01' and date <= '{ym}-{last:02d}'",
            per_page=100, page=page, fieldset="detailed")
        data = r.data or []
        for d in data:
            d = d.to_dict(); e = d.get("entity") or {}
            if name in (e.get("name") or "").upper():
                print(t, d.get("number"), d.get("numeration") or "", str(d["date"])[:10],
                      "| P.IVA salvata:", e.get("vat_number"), "| CF:", e.get("tax_code"),
                      "| ei:", d.get("ei_status"))
        if len(data) < 100:
            break
        page += 1
