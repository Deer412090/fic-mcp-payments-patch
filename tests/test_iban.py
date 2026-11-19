"""IBAN nelle fatture elettroniche (19/11/2026).

Fornaca (mail del 18/11/2026) chiede l'IBAN nella fattura elettronica. I dati
stanno in dati_bancari.json (escluso da git); qui un file finto in tmp_path.
"""

import importlib
import json
import sys
from unittest.mock import MagicMock, patch

import pytest

IBAN = "IT00X0000000000000000000000"   # finto: il repo è pubblico
CLIENT = {"id": 7, "name": "Clinica", "vat_number": "10982360967", "tax_code": "01737940013",
          "address_street": "Via 1", "address_city": "Torino", "address_postal_code": "10128",
          "address_province": "TO", "country": "Italia", "ei_code": "ABC1234", "certified_email": ""}
ITEMS = [{"name": "Prestazioni", "qty": 1, "net_price": 100.0, "vat_id": 45, "vat_value": 0}]


@pytest.fixture
def server(tmp_path, monkeypatch):
    monkeypatch.setenv("FIC_CACHE_DIR", str(tmp_path))
    monkeypatch.setenv("FIC_ACCESS_TOKEN", "test_token")
    monkeypatch.setenv("FIC_COMPANY_ID", "100")
    monkeypatch.setenv("FIC_SENDER_EMAIL", "test@example.invalid")
    for mod in ("server", "cache"):
        sys.modules.pop(mod, None)
    srv = importlib.import_module("server")
    f = tmp_path / "dati_bancari.json"
    f.write_text(json.dumps({"bank_iban": IBAN[:4] + " " + IBAN[4:], "bank_name": "Banca",
                             "bank_beneficiary": "Titolare"}))
    monkeypatch.setattr(srv, "DATI_BANCARI_PATH", str(f))
    return srv


def _resp(payload):
    r = MagicMock()
    r.data.to_dict.return_value = payload
    return r


class FakeFIC:
    def __init__(self, drop_iban=False):
        self.created, self.drop_iban = None, drop_iban

    def get_issued_document(self, company_id, document_id, fieldset=None):
        ei = dict(self.created.get("ei_data") or {})
        if self.drop_iban:
            ei.pop("bank_iban", None)
        return _resp({"id": document_id, "entity": self.created["entity"], "ei_data": ei})

    def create_issued_document(self, company_id, create_issued_document_request):
        self.created = create_issued_document_request["data"]
        return _resp({"id": 999, "number": 1, "date": "2026-11-19"})


def _build(server, fake, doc_type="invoice", **kw):
    with patch.object(server, "issued_api", fake), \
         patch.object(server.clients_api, "get_client", return_value=_resp(CLIENT)), \
         patch.object(server.validation, "validate", return_value=([], [])), \
         patch.object(server, "find_vat_type_id", return_value=45):
        return server.build_issued_document(doc_type=doc_type, client_id=7, items_data=ITEMS,
                                            date_str="2026-11-19", payment_days=30,
                                            visible_subject="", negate_prices=(doc_type == "credit_note"), **kw)


def test_fattura_elettronica_ha_iban(server):
    fake = FakeFIC()
    result, error = _build(server, fake)
    assert error is None, error
    ei = fake.created["ei_data"]
    assert ei["payment_method"] == "MP05" and ei["bank_iban"] == IBAN   # spazi tolti
    assert ei["bank_name"] == "Banca" and ei["bank_beneficiary"] == "Titolare"
    assert result["iban_check"]["salvato"] == IBAN and "iban_warning" not in result


def test_nota_di_credito_senza_iban(server):
    fake = FakeFIC()
    result, error = _build(server, fake, doc_type="credit_note")
    assert error is None, error
    assert fake.created["ei_data"] == {"payment_method": "MP05"}
    assert "iban_check" not in result


def test_controllo_boccia_iban_non_salvato(server):
    """Il controllo deve fallire se FIC scarta il campo in silenzio."""
    result, error = _build(server, FakeFIC(drop_iban=True))
    assert error is None, error
    assert "iban_warning" in result and "nessuno" in result["iban_warning"]


def test_file_mancante_da_avviso(server, monkeypatch, tmp_path):
    monkeypatch.setattr(server, "DATI_BANCARI_PATH", str(tmp_path / "manca.json"))
    fake = FakeFIC()
    result, error = _build(server, fake)
    assert error is None, error
    assert fake.created["ei_data"] == {"payment_method": "MP05"}
    assert "iban_warning" in result


def test_completa_ei_data_non_sovrascrive(server):
    out = server.completa_ei_data({"payment_method": "MP05", "od_number": "PO1"})
    assert out["bank_iban"] == IBAN and out["od_number"] == "PO1"
    keep = server.completa_ei_data({"payment_method": "MP08", "bank_iban": "ALTRO"})
    assert keep["payment_method"] == "MP08" and keep["bank_iban"] == "ALTRO"
