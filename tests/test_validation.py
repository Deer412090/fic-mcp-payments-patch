"""Controllo fiscale: casi costruiti sulle fatture reali del 2026.

Ogni errore che arriva a SdI deve diventare un test qui prima di essere corretto.
"""

import asyncio
import importlib
import json
import sys
from unittest.mock import MagicMock, patch

import pytest

import validation as v

CELLINI = "10982360967"
CDC = "13661780968"
CIDIMU = "03966780011"
SIKELIA = "12117810015"

PREST = {"name": "Prestazioni mediche per vostro conto", "qty": 1, "vat_id": 45, "vat_value": 0}


def bollo(vat_id=21):
    return {"name": "Marca da bollo", "qty": 1, "net_price": 2, "vat_id": vat_id, "vat_value": 0}


def prest(amount):
    return dict(PREST, net_price=amount)


def doc(vat_number, items, net, *, e_invoice=None, doc_type="invoice", **extra):
    d = {
        "type": doc_type,
        "e_invoice": bool(vat_number) if e_invoice is None else e_invoice,
        "vat_number": vat_number,
        "client_name": "test",
        "items": items,
        "payment_total": net,
        "cassa": None,
    }
    d.update(extra)
    return d


def errors_of(d, **kw):
    return v.validate(d, **kw)[0]


# --- fatture corrette già trasmesse: devono passare ---------------------------

@pytest.mark.parametrize("imponibile,net", [
    (4607.79, 3688.23),  # FE167 Cellini Ricoveri SSN maggio
    (2509.77, 2009.82),  # FE173 Cellini Ricoveri SSN giugno
    (1736.26, 1391.01),  # FE179 Cellini Ricoveri SSN luglio (sostituisce FE177)
    (200, 162.00),       # FE178, intervento alla clinica
])
def test_cellini_formula_a_passes(imponibile, net):
    assert errors_of(doc(CELLINI, [prest(imponibile), bollo(21)], net)) == []


@pytest.mark.parametrize("imponibile,net", [
    (333.00, 268.00),    # FE152
    (353.25, 284.20),    # FE153
    (699.50, 561.20),    # FE154
    (1585.75, 1270.20),  # FE168
])
def test_cdc_formula_b_passes(imponibile, net):
    assert errors_of(doc(CDC, [prest(imponibile), bollo(45)], net)) == []


def test_cidimu_ndc9_passes():
    assert errors_of(doc(CIDIMU, [prest(182), bollo(19)], 147.20, doc_type="credit_note")) == []


def test_patient_invoice_passes():
    items = [prest(1213), bollo(21)]
    assert errors_of(doc("", items, 1215.00, e_invoice=False)) == []


def test_patient_visit_under_threshold_without_bollo_passes():
    assert errors_of(doc("", [prest(60)], 60.00, e_invoice=False)) == []


# --- errori reali: devono essere bloccati --------------------------------------

def test_fe177_missing_bollo_is_blocked():
    errs = errors_of(doc(CELLINI, [prest(1736.26)], 1389.01))
    assert any("Manca la marca da bollo" in e for e in errs)


def test_cdc_with_formula_a_is_blocked():
    errs = errors_of(doc(CDC, [prest(333.00), bollo(45)], 268.40))
    assert any("atteso €268.00" in e for e in errs)


def test_cdc_bollo_art15_is_blocked():
    errs = errors_of(doc(CDC, [prest(333.00), bollo(21)], 268.00))
    assert any("vat_id 21" in e and "45" in e for e in errs)


def test_cidimu_bollo_wrong_vat_is_blocked():
    errs = errors_of(doc(CIDIMU, [prest(182), bollo(21)], 147.20))
    assert any("deve essere 19" in e for e in errs)


def test_cellini_ritenuta_on_bollo_is_blocked():
    errs = errors_of(doc(CELLINI, [prest(200), bollo(21)], 161.60))
    assert any("atteso €162.00" in e for e in errs)


def test_patient_with_withholding_is_blocked():
    errs = errors_of(doc("", [prest(1213), bollo(21)], 972.40, e_invoice=False))
    assert any("nessuna ritenuta" in e for e in errs)


def test_patient_electronic_is_blocked():
    errs = errors_of(doc("", [prest(1213), bollo(21)], 1215.00, e_invoice=True))
    assert any("serie F" in e for e in errs)


def test_b2b_not_electronic_is_blocked():
    errs = errors_of(doc(CELLINI, [prest(200), bollo(21)], 162.00, e_invoice=False))
    assert any("elettronica" in e for e in errs)


def test_sikelia_is_blocked():
    errs = errors_of(doc(SIKELIA, [prest(500), bollo(21)], 402.00))
    assert any("Sikelia" in e for e in errs)


def test_vat_22_is_blocked():
    item = dict(prest(100), vat_id=0, vat_value=22)
    errs = errors_of(doc("", [item, bollo(21)], 124.00, e_invoice=False))
    assert any("esenti" in e for e in errs)


def test_bollo_under_threshold_is_blocked():
    errs = errors_of(doc("", [prest(60), bollo(21)], 62.00, e_invoice=False))
    assert any("non dovuta" in e for e in errs)


def test_cassa_not_disabled_is_blocked():
    errs = errors_of(doc(CELLINI, [prest(200), bollo(21)], 162.00, cassa="default FIC"))
    assert any("disable_cassa" in e for e in errs)


def test_electronic_without_fe_numeration_is_blocked_at_creation():
    d = doc(CELLINI, [prest(200), bollo(21)], 162.00, at_creation=True, numeration=None)
    assert any("numeration" in e for e in errors_of(d))


def test_unknown_b2b_client_only_warns_on_withholding():
    d = doc("99999999999", [prest(300), bollo(21)], 242.00)
    errs, warns = v.validate(d)
    assert errs == []
    assert warns and "non è nella tabella" in warns[0]


# --- note di credito ---------------------------------------------------------

def test_ndc10_mirrors_fe177_and_passes():
    fe177 = doc(CELLINI, [prest(1736.26)], 1389.01)
    ndc = doc(CELLINI, [prest(1736.26)], 1389.01, doc_type="credit_note")
    assert errors_of(ndc, source=fe177) == []


def test_credit_note_bigger_than_source_is_blocked():
    src = doc(CELLINI, [prest(200), bollo(21)], 162.00)
    ndc = doc(CELLINI, [prest(300), bollo(21)], 242.00, doc_type="credit_note")
    assert any("superiore" in e for e in errors_of(ndc, source=src))


def test_credit_note_bollo_mismatch_is_blocked():
    src = doc(CELLINI, [prest(200), bollo(21)], 162.00)
    ndc = doc(CELLINI, [prest(200)], 160.00, doc_type="credit_note")
    assert any("speculare" in e for e in errors_of(ndc, source=src))


# --- documento salvato in FIC ---------------------------------------------------

def stored(vat_number, items, net, *, e_invoice=True, stamp_duty=None, doc_type="invoice"):
    return {
        "type": doc_type,
        "e_invoice": e_invoice,
        "entity": {"id": 1, "name": "CASA DI CURA CELLINI S.p.A.", "vat_number": vat_number},
        "items_list": [
            {"name": i["name"], "qty": i["qty"], "net_price": i["net_price"],
             "vat": {"id": i["vat_id"], "value": i["vat_value"]}}
            for i in items
        ],
        "payments_list": [{"amount": net}],
        "cassa": 0,
        "stamp_duty": stamp_duty,
    }


def test_stored_stamp_duty_field_counts_as_bollo():
    d = v.normalize_stored_document(stored(CELLINI, [prest(200)], 162.00, stamp_duty=2))
    assert v.validate(d)[0] == []


def test_stored_patient_invoice_with_document_cassa_field_passes():
    # F15-F49: cassa attiva sul documento ma disattivata per riga, netto corretto 162,00
    s = stored("", [prest(160), bollo(21)], 162.00, e_invoice=False)
    s["cassa"] = 2
    assert v.validate(v.normalize_stored_document(s))[0] == []


def test_stored_fe177_is_blocked():
    d = v.normalize_stored_document(stored(CELLINI, [prest(1736.26)], 1389.01))
    assert any("Manca la marca da bollo" in e for e in v.validate(d)[0])


# --- aggancio al server ----------------------------------------------------------

@pytest.fixture
def server_module(tmp_path, monkeypatch):
    monkeypatch.setenv("FIC_CACHE_DIR", str(tmp_path))
    monkeypatch.setenv("FIC_ACCESS_TOKEN", "test_token")
    monkeypatch.setenv("FIC_COMPANY_ID", "100")
    for mod in ("server", "cache"):
        sys.modules.pop(mod, None)
    return importlib.import_module("server")


def _get(stored_doc, ei_status="not_sent"):
    resp = MagicMock()
    resp.data.to_dict.return_value = dict(stored_doc, ei_status=ei_status, number=177)
    return resp


def test_send_to_sdi_blocks_fe177(server_module):
    s = server_module
    with patch.object(s.issued_api, "get_issued_document",
                      return_value=_get(stored(CELLINI, [prest(1736.26)], 1389.01))), \
         patch.object(s.einvoice_api, "send_e_invoice") as send:
        out = json.loads(asyncio.run(s.call_tool("send_to_sdi", {"document_id": 1}))[0].text)
    assert out["success"] is False
    assert "Manca la marca da bollo" in out["error"]
    assert send.call_count == 0


def test_send_to_sdi_allows_fe179(server_module):
    s = server_module
    with patch.object(s.issued_api, "get_issued_document",
                      return_value=_get(stored(CELLINI, [prest(1736.26), bollo(21)], 1391.01))), \
         patch.object(s.einvoice_api, "send_e_invoice") as send:
        out = json.loads(asyncio.run(s.call_tool("send_to_sdi", {"document_id": 1}))[0].text)
    assert out["success"] is True
    assert send.call_count == 1


def test_create_invoice_without_bollo_never_reaches_fic(server_module):
    s = server_module
    client = MagicMock()
    client.data.to_dict.return_value = {"id": 110785934, "name": "CASA DI CURA CELLINI S.p.A.",
                                        "vat_number": CELLINI, "ei_code": "MZO2A0U"}
    with patch.object(s.clients_api, "get_client", return_value=client), \
         patch.object(s.issued_api, "create_issued_document") as create:
        out = json.loads(asyncio.run(s.call_tool("create_invoice", {
            "client_id": 110785934, "electronic": True, "numeration": "FE", "disable_cassa": True,
            "items": [{"name": "Prestazioni mediche per vostro conto", "qty": 1,
                       "net_price": 1736.26, "vat_id": 45}],
        }))[0].text)
    assert out["success"] is False
    assert "Manca la marca da bollo" in out["error"]
    assert create.call_count == 0


def test_create_invoice_fe179_reaches_fic(server_module):
    s = server_module
    client = MagicMock()
    client.data.to_dict.return_value = {"id": 110785934, "name": "CASA DI CURA CELLINI S.p.A.",
                                        "vat_number": CELLINI, "ei_code": "MZO2A0U"}
    created = MagicMock()
    created.data.to_dict.return_value = {"id": 553274171, "number": 179, "date": "2026-09-17"}
    with patch.object(s.clients_api, "get_client", return_value=client), \
         patch.object(s.issued_api, "create_issued_document", return_value=created) as create:
        out = json.loads(asyncio.run(s.call_tool("create_invoice", {
            "client_id": 110785934, "electronic": True, "numeration": "FE", "disable_cassa": True,
            "items": [{"name": "Prestazioni mediche per vostro conto", "qty": 1,
                       "net_price": 1736.26, "vat_id": 45},
                      {"name": "Marca da bollo", "qty": 1, "net_price": 2, "vat_id": 21}],
        }))[0].text)
    assert out["success"] is True
    body = create.call_args.kwargs["create_issued_document_request"]["data"]
    assert body["payments_list"][0]["amount"] == 1391.01
