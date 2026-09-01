# Known Issues

## Duplicate invoice fails for some clients

`duplicate_invoice` may fail on specific client configurations. Symptom, exact error and reproducibility pattern not yet captured.

**Workaround:** duplicate the invoice manually from the FattureInCloud web panel.

**Status:** investigation pending — target patch release once a reproducible case is collected. To help: report the source invoice ID and the exact error message at https://github.com/aringad/fattureincloud-mcp/issues

## `mark_as_paid` fails on e-invoices already transmitted to SdI

`mark_as_paid` calls `modify_issued_document` with a body that always includes `items_list`. FattureInCloud rejects this with `409 "The document is locked. Cannot edit items_list core data."` on any document with `ei_status` set (i.e. already sent to SdI) — the lock applies specifically to `items_list`, not to the whole document.

A second, related bug: the payment total is computed as `sum(qty * net_price for items in items_list)`, which ignores the marca da bollo when it's stored as document-level `stamp_duty` rather than a line item. This causes a `422 "totale pagamenti non corrisponde"` on documents where the bollo isn't a line.

**Workaround:** mark the invoice as paid manually from the FattureInCloud web panel.

**Planned fix:** since `items_list` and `payments_list` are both `Optional[...] = None` on the `IssuedDocument` model and the SDK's serialization omits unset fields, a request touching only `payments_list` (omitting `items_list` entirely) should bypass the lock on already-transmitted documents. The total should also add `stamp_duty` when present. Not yet implemented — tracked internally.
