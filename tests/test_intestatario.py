"""Intestatario delle fatture e delle NDC (correzione del 17/11/2026).

Caso reale: FE155-159 Cellini (09/07/2026) uscirono con la vecchia P.IVA 00510380017
perché la cache cliente (24 ore) non era stata svuotata dopo update_client; la NDC 11
del 17/11 uscì invece con la P.IVA nuova perché create_credit_note rileggeva l'anagrafica.
"""

import asyncio
import importlib
import json
import sys
from unittest.mock import MagicMock, patch

import pytest

OLD_VAT = "00510380017"
NEW_VAT = "10982360967"
CLIENT_ID = 7


@pytest.fixture
def server(tmp_path, monkeypatch):
    monkeypatch.setenv("FIC_CACHE_DIR", str(tmp_path))
    monkeypatch.delenv("FIC_CACHE_DISABLED", raising=False)
    monkeypatch.setenv("FIC_ACCESS_TOKEN", "test_token")
    monkeypatch.setenv("FIC_COMPANY_ID", "100")
    monkeypatch.setenv("FIC_SENDER_EMAIL", "test@example.invalid")
    for mod in ("server", "cache"):
        sys.modules.pop(mod, None)
    return importlib.import_module("server")


def _client(vat):
    return {"id": CLIENT_ID, "name": "Humanitas Cellini", "vat_number": vat, "tax_code": vat,
            "address_street": "Via Cellini 5", "address_city": "Torino",
            "address_postal_code": "10126", "address_province": "TO", "country": "Italia",
            "ei_code": "ABC1234", "certified_email": ""}


def _resp(payload):
    r = MagicMock()
    r.data.to_dict.return_value = payload
    return r


class FakeFIC:
    """issued_api finto: salva il corpo creato e lo restituisce alla rilettura."""

    def __init__(self, source_doc=None):
        self.source_doc = source_doc
        self.created = None

    def get_issued_document(self, company_id, document_id, fieldset=None):
        if self.source_doc and document_id == self.source_doc["id"]:
            return _resp(self.source_doc)
        return _resp({"id": document_id, "entity": self.created["entity"]})

    def create_issued_document(self, company_id, create_issued_document_request):
        self.created = create_issued_document_request["data"]
        return _resp({"id": 999, "number": 11, "date": "2026-11-17"})


ITEMS = [{"name": "Intervento chirurgico", "qty": 1, "net_price": 402.0, "vat_id": 45, "vat_value": 0}]


def _run(server, fake, fresh_client, fn):
    with patch.object(server, "issued_api", fake), \
         patch.object(server.clients_api, "get_client", return_value=_resp(fresh_client)), \
         patch.object(server.validation, "validate", return_value=([], [])), \
         patch.object(server, "find_vat_type_id", return_value=45):
        return fn()


# (a) NDC speculare -----------------------------------------------------------

def test_ndc_copia_intestatario_dalla_fattura_stornata(server):
    source = {"id": 155, "type": "invoice", "entity": _client("IT" + OLD_VAT), "items_list": [],
              "payments_list": [], "e_invoice": True}
    fake = FakeFIC(source_doc=source)
    result, error = _run(server, fake, _client(NEW_VAT), lambda: server.build_issued_document(
        doc_type="credit_note", client_id=CLIENT_ID, items_data=ITEMS, date_str="2026-11-17",
        payment_days=30, visible_subject="Storno FE155", negate_prices=True, source_invoice_id=155))
    assert error is None, error
    assert fake.created["entity"]["vat_number"] == "IT" + OLD_VAT      # come la fattura, non l'anagrafica
    assert fake.created["original_document"] == {"id": 155}
    assert result["intestatario_check"]["confrontato_con"].startswith("fattura stornata 155")
    assert "intestatario_warning" not in result                          # speculare = nessun avviso


def test_ndc_senza_source_usa_anagrafica(server):
    fake = FakeFIC()
    result, error = _run(server, fake, _client(NEW_VAT), lambda: server.build_issued_document(
        doc_type="credit_note", client_id=CLIENT_ID, items_data=ITEMS, date_str="2026-11-17",
        payment_days=30, visible_subject="", negate_prices=True))
    assert error is None, error
    assert fake.created["entity"]["vat_number"] == NEW_VAT


def test_ndc_su_fattura_di_altro_cliente_si_ferma(server):
    other = dict(_client(OLD_VAT), id=8, name="Altro")
    fake = FakeFIC(source_doc={"id": 155, "entity": other, "items_list": [], "payments_list": []})
    result, error = _run(server, fake, _client(NEW_VAT), lambda: server.build_issued_document(
        doc_type="credit_note", client_id=CLIENT_ID, items_data=ITEMS, date_str="2026-11-17",
        payment_days=30, visible_subject="", negate_prices=True, source_invoice_id=155))
    assert result is None and "cliente 8" in error
    assert fake.created is None


# (b) update_client svuota la cache ---------------------------------------------

def test_update_client_invalida_la_cache(server):
    server.cache.put(f"client_{CLIENT_ID}", server.COMPANY_ID, _client(OLD_VAT))
    path = server.cache._cache_path(f"client_{CLIENT_ID}", server.COMPANY_ID)
    assert path.exists()
    with patch.object(server.clients_api, "modify_client", return_value=_resp(_client(NEW_VAT))):
        out = asyncio.run(server.call_tool("update_client", {"client_id": CLIENT_ID, "vat_number": NEW_VAT}))
    assert json.loads(out[0].text)["success"] is True
    assert not path.exists(), "la cache del cliente deve sparire dopo update_client"
    # e la lettura successiva porta il dato nuovo
    with patch.object(server.clients_api, "get_client", return_value=_resp(_client(NEW_VAT))):
        assert server.get_client_by_id(CLIENT_ID)["vat_number"] == NEW_VAT


# (c) il controllo DEVE fallire sul caso reale ---------------------------------

def test_confronto_boccia_vecchia_piva_cellini(server):
    diff = server.validation.confronta_intestatario({"vat_number": OLD_VAT, "tax_code": OLD_VAT},
                                                    {"vat_number": NEW_VAT, "tax_code": NEW_VAT})
    assert len(diff) == 2 and OLD_VAT in diff[0] and NEW_VAT in diff[0]


def test_confronto_ignora_prefisso_IT_e_spazi(server):
    assert server.validation.confronta_intestatario({"vat_number": "IT 10982360967"},
                                                    {"vat_number": NEW_VAT}) == []


def test_fattura_con_cache_vecchia_da_avviso(server):
    """Il 09/07: anagrafica FIC già corretta, cache ancora con la P.IVA vecchia."""
    server.cache.put(f"client_{CLIENT_ID}", server.COMPANY_ID, _client(OLD_VAT))
    fake = FakeFIC()
    result, error = _run(server, fake, _client(NEW_VAT), lambda: server.build_issued_document(
        doc_type="invoice", client_id=CLIENT_ID, items_data=ITEMS, date_str="2026-07-09",
        payment_days=30, visible_subject=""))
    assert error is None, error
    assert fake.created["entity"]["vat_number"] == OLD_VAT          # il difetto riprodotto
    assert "intestatario_warning" in result, "il controllo doveva bocciare la P.IVA vecchia"
    assert OLD_VAT in result["intestatario_warning"] and NEW_VAT in result["intestatario_warning"]


def test_fattura_corretta_nessun_avviso(server):
    fake = FakeFIC()
    result, error = _run(server, fake, _client(NEW_VAT), lambda: server.build_issued_document(
        doc_type="invoice", client_id=CLIENT_ID, items_data=ITEMS, date_str="2026-11-17",
        payment_days=30, visible_subject=""))
    assert error is None, error
    assert result["intestatario_check"]["differenze"] == []
    assert "intestatario_warning" not in result
