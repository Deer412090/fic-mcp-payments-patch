"""Sola lettura: applica validation.validate a tutti i documenti emessi 2026 in FIC.

Uso: venv/bin/python scripts/audit_validation.py
Legge token e company id dalla configurazione MCP dell app Claude (non li stampa).
"""
import json, os, sys
cfg = json.load(open(os.path.expanduser("~/Library/Application Support/Claude/claude_desktop_config.json")))
os.environ.update(cfg["mcpServers"]["fattureincloud"]["env"])
os.environ["FIC_CACHE_DISABLED"] = "1"
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import server, validation

def fetch(doc_type):
    out, page = [], 1
    while True:
        r = server.issued_api.list_issued_documents(company_id=server.COMPANY_ID, type=doc_type,
            q="date >= '2026-01-01' and date <= '2026-12-31'", per_page=100, page=page, fieldset="detailed")
        data = r.data or []
        out += [d.to_dict() for d in data]
        if len(data) < 100: break
        page += 1
    return out

summary = {}
for t in ("invoice", "credit_note"):
    docs = fetch(t)
    ok = 0
    for d in sorted(docs, key=lambda x: (str(x.get("numeration") or ""), x.get("number") or 0)):
        full = server.issued_api.get_issued_document(company_id=server.COMPANY_ID, document_id=d["id"], fieldset="detailed").data.to_dict()
        n = validation.normalize_stored_document(full)
        errs, warns = validation.validate(n)
        tag = f"{t} {full.get('number')}{full.get('numeration') or ''} {str(full.get('date'))[:10]} ei={full.get('ei_status')} stato_pag={[str(p.get('status')).split('.')[-1] for p in (full.get('payments_list') or [])]}"
        if errs or warns:
            print("---", tag, "|", (n['client_name'] or '')[:30], "| P.IVA:", n['vat_number'] or "-", "| netto:", n['payment_total'])
            for e in errs: print("   ERR", e)
            for w in warns: print("   WARN", w)
        else:
            ok += 1
    summary[t] = (len(docs), ok)
    print(f"== {t}: {len(docs)} documenti, {ok} senza rilievi")
print(summary)
