"""Controlli fiscali bloccanti prima di creare, finalizzare o inviare un documento.

Fonte delle regole: Regole_fatturazione_Vasario.md e CLAUDE.md di progetto.
Una regola nuova si aggiunge qui (con un test), non solo nelle guide.
"""

BOLLO_AMOUNT = 2.0
BOLLO_THRESHOLD = 77.47
WITHHOLDING_RATE = 0.20
BOLLO_VAT_ID_DEFAULT = 21  # art. 15 DPR 633/72
TOLERANCE = 0.011

# P.IVA → regole cliente. Cellini compare anche col CF perché il vecchio client FIC
# era stato creato con P.IVA = CF (corretto il 09/07/2026).
CLIENT_RULES = {
    "10982360967": {"name": "Cellini", "bollo_vat_id": 21, "withholding_on_bollo": False},
    "00510380017": {"name": "Cellini", "bollo_vat_id": 21, "withholding_on_bollo": False},
    "01737940013": {"name": "Fornaca/ECAS", "bollo_vat_id": 21, "withholding_on_bollo": False},
    "09647040014": {"name": "Fisio&Lab", "bollo_vat_id": 21, "withholding_on_bollo": False},
    # CDC: confermato per iscritto il 07/07/2026 (bollo stesso codice N.4 della prestazione).
    # 03954980011 è il CF, che le Regole riportavano per errore nella colonna P.IVA.
    "13661780968": {"name": "CDC", "bollo_vat_id": 45, "withholding_on_bollo": True},
    "03954980011": {"name": "CDC", "bollo_vat_id": 45, "withholding_on_bollo": True},
    "03966780011": {"name": "Cidimu", "bollo_vat_id": 19, "withholding_on_bollo": True},
}

BLOCKED_CLIENTS = {
    "12117810015": "Sikelia SRL emette le fatture in nome e per conto di Gab: mai emetterle da FIC",
}


def _num(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _enum_str(value):
    s = str(value or "")
    return s.split(".")[-1].lower() if "." in s else s.lower()


def is_bollo(item):
    return "bollo" in (item.get("name") or "").lower()


def normalize_items(items_list):
    """Accetta sia righe in formato body FIC ({vat: {id, value}}) sia già normalizzate."""
    out = []
    for i in items_list or []:
        vat = i.get("vat") or {}
        if hasattr(vat, "to_dict"):
            vat = vat.to_dict()
        out.append({
            "name": i.get("name") or "",
            "qty": _num(i.get("qty", 1)),
            "net_price": abs(_num(i.get("net_price"))),
            "vat_id": vat.get("id") if isinstance(vat, dict) else i.get("vat_id"),
            "vat_value": _num(vat.get("value")) if isinstance(vat, dict) else _num(i.get("vat_value")),
        })
    return out


def normalize_stored_document(d):
    """Da `issued_api.get_issued_document(...).data.to_dict()` al formato del validatore."""
    entity = d.get("entity") or {}
    if hasattr(entity, "to_dict"):
        entity = entity.to_dict()
    payments = d.get("payments_list") or []
    payment_total = 0.0
    for p in payments:
        if hasattr(p, "to_dict"):
            p = p.to_dict()
        payment_total += abs(_num(p.get("amount")))
    items = normalize_items(d.get("items_list"))
    # Documenti creati dal sito FIC possono avere il bollo come campo e non come riga.
    stamp = abs(_num(d.get("stamp_duty")))
    if stamp > 0 and not any(is_bollo(i) for i in items):
        items.append({"name": "Marca da bollo (campo stamp_duty)", "qty": 1.0, "net_price": stamp,
                      "vat_id": None, "vat_value": 0.0, "stamp_field": True})
    return {
        "type": _enum_str(d.get("type")) or "invoice",
        "e_invoice": bool(d.get("e_invoice")),
        "vat_number": (entity.get("vat_number") or "").strip(),
        "client_name": entity.get("name") or "",
        "items": items,
        "payment_total": round(payment_total, 2),
        # Il campo `cassa` del documento può essere attivo e disattivato riga per riga
        # (fatture pazienti dal form): l'effetto reale lo misura già il netto.
        "cassa": None,
        "numeration": d.get("numeration"),
    }


def expected_net(items, withholding, withholding_on_bollo):
    imponibile = sum(i["qty"] * i["net_price"] for i in items if not is_bollo(i))
    bollo = sum(i["qty"] * i["net_price"] for i in items if is_bollo(i))
    if not withholding:
        return round(imponibile + bollo, 2)
    base = imponibile + (bollo if withholding_on_bollo else 0)
    return round(imponibile + bollo - base * WITHHOLDING_RATE, 2)


def validate(doc, *, source=None):
    """Ritorna (errori, avvisi). Gli errori bloccano l'operazione.

    `doc` è normalizzato (normalize_stored_document o costruito dal chiamante).
    `source` è il documento originale normalizzato quando si crea una nota di credito.
    """
    errors, warnings = [], []
    doc_type = doc.get("type", "invoice")
    if doc_type not in ("invoice", "credit_note"):
        return errors, warnings

    vat_number = doc.get("vat_number") or ""
    items = doc.get("items") or []
    is_b2b = bool(vat_number)
    rules = CLIENT_RULES.get(vat_number)

    if vat_number in BLOCKED_CLIENTS:
        errors.append(BLOCKED_CLIENTS[vat_number])
        return errors, warnings

    if not items:
        errors.append("Documento senza righe.")
        return errors, warnings

    for i in items:
        if i["vat_value"] != 0:
            errors.append(
                f"Riga '{i['name']}' con IVA {i['vat_value']:g}%: le prestazioni sanitarie sono esenti "
                "(prestazione vat_id 45, art. 10 n. 18)."
            )

    cassa = doc.get("cassa")
    if cassa not in (None, 0, 0.0, "0"):
        errors.append("Cassa previdenziale applicata: serve disable_cassa=True.")

    if is_b2b and not doc.get("e_invoice"):
        errors.append(f"Cliente con P.IVA ({doc.get('client_name')}): la fattura deve essere elettronica (serie FE, SdI).")
    if not is_b2b and doc.get("e_invoice"):
        errors.append(f"Cliente senza P.IVA ({doc.get('client_name')}): fattura al paziente, serie F non elettronica.")

    # Solo in creazione: il formato di `numeration` sul documento salvato non è stato verificato.
    if doc.get("at_creation") and doc_type == "invoice":
        if doc.get("e_invoice") and doc.get("numeration") != "FE":
            errors.append('Fattura elettronica senza numeration="FE": finirebbe nel sezionale dei pazienti (errore del 07/07/2026).')
        if not doc.get("e_invoice") and doc.get("numeration") == "FE":
            errors.append('numeration="FE" su fattura non elettronica: la serie FE è solo per le fatture SdI.')

    bollo_items = [i for i in items if is_bollo(i)]
    imponibile = sum(i["qty"] * i["net_price"] for i in items if not is_bollo(i))

    if len(bollo_items) > 1:
        errors.append("Più di una riga marca da bollo.")
    for b in bollo_items:
        if abs(b["qty"] * b["net_price"] - BOLLO_AMOUNT) > TOLERANCE:
            errors.append(f"Marca da bollo di €{b['qty'] * b['net_price']:.2f}: deve essere €2,00.")
        expected_vat_id = rules["bollo_vat_id"] if rules else BOLLO_VAT_ID_DEFAULT
        if not b.get("stamp_field") and b["vat_id"] != expected_vat_id:
            who = rules["name"] if rules else ("paziente" if not is_b2b else "cliente")
            errors.append(
                f"Bollo con vat_id {b['vat_id']}: per {who} deve essere {expected_vat_id} (Regole, tabella clienti)."
            )

    if doc_type == "invoice":
        if imponibile > BOLLO_THRESHOLD and not bollo_items:
            errors.append(
                f"Manca la marca da bollo: imponibile esente €{imponibile:.2f} > €77,47. "
                "Va sempre aggiunta come riga separata, anche se il conteggio della clinica scrive "
                "'Bollo € 0,00' (errore FE177 del 17/09/2026)."
            )
        if imponibile <= BOLLO_THRESHOLD and bollo_items:
            errors.append(f"Marca da bollo su imponibile €{imponibile:.2f} ≤ €77,47: non dovuta.")

    if is_b2b and rules is None:
        warnings.append(
            f"P.IVA {vat_number} ({doc.get('client_name')}) non è nella tabella regole di validation.py: "
            "controllati solo bollo, IVA e cassa, non la base della ritenuta."
        )
    else:
        withholding = is_b2b
        on_bollo = bool(rules and rules["withholding_on_bollo"])
        expected = expected_net(items, withholding, on_bollo)
        actual = doc.get("payment_total")
        if actual is not None and abs(actual - expected) > TOLERANCE:
            if withholding:
                formula = "0,8×(imponibile+bollo)" if on_bollo else "0,8×imponibile + bollo"
                detail = f"ritenuta 20% per {rules['name']}: {formula}"
            else:
                detail = "paziente: nessuna ritenuta"
            errors.append(
                f"Netto da pagare €{actual:.2f}, atteso €{expected:.2f} ({detail})."
            )

    if doc_type == "credit_note" and source is not None:
        src_net = source.get("payment_total")
        own_net = doc.get("payment_total")
        src_has_bollo = any(is_bollo(i) for i in source.get("items") or [])
        if bool(bollo_items) != src_has_bollo:
            errors.append("Nota di credito non speculare: bollo presente in uno solo dei due documenti.")
        if src_net is not None and own_net is not None:
            if own_net - src_net > TOLERANCE:
                errors.append(f"Nota di credito €{own_net:.2f} superiore alla fattura stornata €{src_net:.2f}.")
            elif src_net - own_net > TOLERANCE:
                warnings.append(f"Storno parziale: NDC €{own_net:.2f} su fattura €{src_net:.2f}.")

    return errors, warnings


def format_block(errors, warnings, action):
    lines = [f"BLOCCATO dal controllo fiscale ({action}). Correggere e riprovare:"]
    lines += [f"- {e}" for e in errors]
    if warnings:
        lines.append("Avvisi:")
        lines += [f"- {w}" for w in warnings]
    return "\n".join(lines)
