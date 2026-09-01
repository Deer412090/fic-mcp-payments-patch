# Known Issues

## Duplicate invoice fails for some clients

`duplicate_invoice` may fail on specific client configurations. Symptom, exact error and reproducibility pattern not yet captured.

**Workaround:** duplicate the invoice manually from the FattureInCloud web panel.

**Status:** investigation pending — target patch release once a reproducible case is collected. To help: report the source invoice ID and the exact error message at https://github.com/aringad/fattureincloud-mcp/issues

## ~~`mark_as_paid` fails on e-invoices already transmitted to SdI~~ — fixed

**Status: resolved.** Three distinct bugs were involved; all are fixed and verified against real documents.

### Bug A — `409` on every document already sent to SdI

The request body always included `items_list`. FattureInCloud rejects that with
`409 "The document is locked. Cannot edit items_list core data."` whenever
`ei_status` is set. The lock applies specifically to `items_list`, not to the
whole document.

### Bug B — `422` from a recomputed payment total

The total was computed as `sum(qty * net_price)` over the line items. That
ignores the document-level `stamp_duty` (marca da bollo stored as a document
field rather than as a line), and it also ignores withholding tax, producing a
`422 "totale pagamenti non corrisponde"`.

### Bug C — `422` on non-electronic documents, from rebuilding the document

The non-electronic path rebuilt the whole document from its line items, copying
only `name`, `description`, `qty`, `net_price` and `vat`. The per-line flags
`apply_cassa` and `apply_withholding_taxes` were lost, the server re-defaulted
them to "apply", and the amount due changed (e.g. 162.00 → 133.20), so the
payment no longer matched. This affected every document carrying
document-level `cassa` / `withholding_tax` defaults that are disabled per line —
a very common shape for B2C invoices. It was masked until Bug A was fixed,
because the 409 stopped e-invoices before this path was ever reached.

### The fix

`mark_as_paid` now issues a **partial PUT** carrying only `payments_list`, for
every document, and takes the amount from the stored `payments_list[0].amount`
instead of recomputing it. Marking a payment never touches the line items.

**On PUT semantics.** The API reference documents this endpoint only as
"Modifies the specified document" and does not state whether omitted fields are
preserved. Verified empirically with `get_existing_issued_document_totals`
(a read-only endpoint that computes the totals of a *proposed* modification) on
an **unlocked** document: a body containing only `payments_list` still returned
`amount_net: 160` with cassa and withholding at their real values, and
`amount_due` equal to the payments sum. **The PUT merges onto the stored
document; it does not replace it.**

### Not covered

- Documents with more than one payment instalment: `mark_as_paid` refuses
  explicitly rather than collapsing the schedule into a single payment.
- Credit notes and proformas: accepted by the tool, never exercised.
- Documents with no `payments_list` at all: the amount falls back to
  `sum(items) + stamp_duty`; this path is untested.
