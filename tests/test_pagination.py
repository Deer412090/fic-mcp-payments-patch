"""Le liste FIC restituiscono al massimo per_page (100) elementi per chiamata.
get_situation, list_invoices, list_clients e list_received_documents devono
seguire la paginazione: nel 2026 le fatture hanno superato le 100 e quelle
oltre la prima pagina sparivano in silenzio dai totali.
"""

import asyncio
import importlib
import json
import sys

import pytest
from unittest.mock import patch


@pytest.fixture
def server_module(tmp_path, monkeypatch):
    monkeypatch.setenv("FIC_CACHE_DIR", str(tmp_path))
    monkeypatch.setenv("FIC_ACCESS_TOKEN", "test_token")
    monkeypatch.setenv("FIC_COMPANY_ID", "100")

    for mod in ("server", "cache"):
        if mod in sys.modules:
            del sys.modules[mod]

    yield importlib.import_module("server")


class _Doc:
    def __init__(self, d):
        self._d = d

    def to_dict(self):
        return self._d


class _Page:
    def __init__(self, data, last_page):
        self.data = data
        self.last_page = last_page


class FakeListApi:
    """API finta: restituisce `items` a pagine di per_page e registra le chiamate."""

    def __init__(self, items_by_type):
        self.items_by_type = items_by_type
        self.calls = []

    def list(self, **kwargs):
        self.calls.append(kwargs)
        items = self.items_by_type.get(kwargs.get("type"), [])
        per_page = kwargs["per_page"]
        page = kwargs.get("page", 1)
        last_page = max(1, -(-len(items) // per_page))
        chunk = items[(page - 1) * per_page: page * per_page]
        return _Page([_Doc(i) for i in chunk], last_page)


def _invoice(n, client, amount, status="NOT_PAID"):
    return {
        "id": n, "number": n, "date": "2026-09-25",
        "entity": {"name": client},
        "payments_list": [{"amount": amount, "status": status, "due_date": f"2026-10-{(n % 28) + 1:02d}"}],
    }


def _call(server, name, args):
    out = asyncio.run(server.call_tool(name, args))
    return json.loads(out[0].text)


def _invoices_107():
    docs = [_invoice(n, "CLINICA", 100.0) for n in range(1, 107)]
    # l'ultima sta a pagina 2: e' il caso ADAGE del 02/10/2026
    docs.append(_invoice(107, "ADAGE NICOLO'", 252.0))
    return docs


def test_get_situation_legge_tutte_le_pagine(server_module):
    server = server_module
    issued = FakeListApi({"invoice": _invoices_107(), "credit_note": []})
    received = FakeListApi({"expense": [{"amount_gross": 10.0}] * 150})

    with patch.object(server.issued_api, "list_issued_documents", side_effect=issued.list), \
         patch.object(server.received_api, "list_received_documents", side_effect=received.list):
        result = _call(server, "get_situation", {"year": 2026})

    assert result["numero_fatture"] == 107
    assert result["fatturato_lordo"] == 106 * 100.0 + 252.0
    assert result["costi_totali"] == 1500.0
    assert result["numero_non_pagate"] == 107
    assert len(result["prossime_scadenze"]) == 10
    assert [c.get("page", 1) for c in issued.calls if c["type"] == "invoice"] == [1, 2]
    assert [c.get("page", 1) for c in issued.calls if c["type"] == "credit_note"] == [1]


def test_get_situation_filtro_cliente_oltre_pagina_uno(server_module):
    server = server_module
    issued = FakeListApi({"invoice": _invoices_107(), "credit_note": []})

    with patch.object(server.issued_api, "list_issued_documents", side_effect=issued.list):
        result = _call(server, "get_situation", {"year": 2026, "client_name": "ADAGE"})

    assert result["numero_fatture"] == 1
    assert result["fatturato_lordo"] == 252.0


def test_get_situation_all_unpaid_elenco_completo(server_module):
    server = server_module
    issued = FakeListApi({"invoice": _invoices_107(), "credit_note": []})
    received = FakeListApi({"expense": []})

    with patch.object(server.issued_api, "list_issued_documents", side_effect=issued.list), \
         patch.object(server.received_api, "list_received_documents", side_effect=received.list):
        result = _call(server, "get_situation", {"year": 2026, "all_unpaid": True})

    assert len(result["prossime_scadenze"]) == 107
    assert round(sum(r["amount"] for r in result["prossime_scadenze"]), 2) == result["da_incassare"]


def test_list_invoices_senza_mese_legge_tutte_le_pagine(server_module):
    server = server_module
    issued = FakeListApi({"invoice": _invoices_107()})

    with patch.object(server.issued_api, "list_issued_documents", side_effect=issued.list):
        tutte = _call(server, "list_invoices", {"year": 2026})
        adage = _call(server, "list_invoices", {"year": 2026, "query": "adage"})

    assert len(tutte) == 107
    assert [i["number"] for i in adage] == [107]


def test_list_clients_legge_tutte_le_pagine(server_module):
    server = server_module
    api = FakeListApi({None: [{"id": n, "name": f"Cliente {n}"} for n in range(1, 131)]})

    with patch.object(server.clients_api, "list_clients", side_effect=api.list):
        tutti = _call(server, "list_clients", {})
        uno = _call(server, "list_clients", {"query": "Cliente 130"})

    assert len(tutti) == 130
    assert [c["id"] for c in uno] == [130]


def test_list_received_documents_legge_tutte_le_pagine(server_module):
    server = server_module
    api = FakeListApi({"expense": [{"id": n, "number": n, "amount_gross": 1.0} for n in range(1, 151)]})

    with patch.object(server.received_api, "list_received_documents", side_effect=api.list):
        docs = _call(server, "list_received_documents", {"year": 2026})

    assert len(docs) == 150
