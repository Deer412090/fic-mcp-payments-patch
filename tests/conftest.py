"""I test non devono leggere il dati_bancari.json reale (IBAN dello studio):
senza questo, un test di send_to_sdi chiamerebbe FIC per aggiungere l'IBAN."""

import pytest


@pytest.fixture(autouse=True)
def _niente_dati_bancari_reali(tmp_path, monkeypatch):
    monkeypatch.setenv("FIC_DATI_BANCARI", str(tmp_path / "nessun_dati_bancari.json"))
