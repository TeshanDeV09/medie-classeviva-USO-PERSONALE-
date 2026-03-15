"""
tests/test_backend.py
Unit test per logica backend: medie, normalizzazione voti, CSV.
"""

import csv
import io
import json
import os
import sys
import time
import unittest
from unittest.mock import MagicMock, patch

# Aggiungi la root al path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from classeviva_client import ClasseVivaClient, AuthError, NetworkError, ThrottleError


# ── Fixtures ──────────────────────────────────────────────────────────────────

SAMPLE_VOTI = [
    {"materia": "Matematica", "data": "2024-10-05", "tipo": "verifica", "valore": 7.5, "periodo": 1, "note": ""},
    {"materia": "Matematica", "data": "2024-11-12", "tipo": "scritto",  "valore": 6.0, "periodo": 1, "note": ""},
    {"materia": "Matematica", "data": "2025-02-10", "tipo": "verifica", "valore": 8.0, "periodo": 2, "note": ""},
    {"materia": "Italiano",   "data": "2024-10-08", "tipo": "orale",    "valore": 7.0, "periodo": 1, "note": ""},
    {"materia": "Italiano",   "data": "2025-03-15", "tipo": "orale",    "valore": 8.5, "periodo": 2, "note": ""},
]

SAMPLE_JSON = {
    "student": {"id": "S001", "nome": "Test User", "classe": "4AI"},
    "voti": SAMPLE_VOTI,
}


# ── Test ClasseVivaClient ──────────────────────────────────────────────────────

class TestCacheAndThrottle(unittest.TestCase):

    def setUp(self):
        self.client = ClasseVivaClient()

    def test_cache_initially_invalid(self):
        self.assertFalse(self.client._is_cache_valid())

    def test_cache_valid_after_set(self):
        self.client._set_cache(SAMPLE_JSON)
        self.assertTrue(self.client._is_cache_valid())

    def test_cache_age_after_set(self):
        self.client._set_cache(SAMPLE_JSON)
        age = self.client.get_cache_age_seconds()
        self.assertIsNotNone(age)
        self.assertLess(age, 5)

    def test_cache_invalidated(self):
        self.client._set_cache(SAMPLE_JSON)
        self.client.invalidate_cache()
        self.assertFalse(self.client._is_cache_valid())

    def test_throttle_raises_if_too_soon(self):
        from datetime import datetime
        self.client._last_request = datetime.now()
        with self.assertRaises(ThrottleError):
            self.client._check_throttle()

    def test_throttle_passes_after_delay(self):
        from datetime import datetime, timedelta
        self.client._last_request = datetime.now() - timedelta(seconds=100)
        # Should not raise
        self.client._check_throttle()

    def test_fetch_from_cache_when_valid(self):
        self.client._set_cache(SAMPLE_JSON)
        # Non deve fare chiamate API; sostituisce con mock
        self.client._fetch_grades_from_api = MagicMock()
        result = self.client.fetch_voti(force_refresh=False)
        self.client._fetch_grades_from_api.assert_not_called()
        self.assertEqual(result, SAMPLE_JSON)


class TestAuthErrors(unittest.TestCase):

    def test_login_fails_without_credentials(self):
        client = ClasseVivaClient()
        client.username = ""
        client.password = ""
        with self.assertRaises(AuthError):
            client.login()


class TestNormalizeTipo(unittest.TestCase):

    def test_scritto(self):
        self.assertEqual(ClasseVivaClient._normalize_tipo("scritto"), "scritto")
        self.assertEqual(ClasseVivaClient._normalize_tipo("compito in classe"), "scritto")
        self.assertEqual(ClasseVivaClient._normalize_tipo("written test"), "scritto")

    def test_orale(self):
        self.assertEqual(ClasseVivaClient._normalize_tipo("orale"), "orale")
        self.assertEqual(ClasseVivaClient._normalize_tipo("oral"), "orale")

    def test_verifica(self):
        self.assertEqual(ClasseVivaClient._normalize_tipo("verifica"), "verifica")
        self.assertEqual(ClasseVivaClient._normalize_tipo("test"), "verifica")

    def test_pratico(self):
        self.assertEqual(ClasseVivaClient._normalize_tipo("pratico"), "pratico")
        self.assertEqual(ClasseVivaClient._normalize_tipo("lab"), "pratico")

    def test_altro(self):
        self.assertEqual(ClasseVivaClient._normalize_tipo(""), "altro")
        self.assertEqual(ClasseVivaClient._normalize_tipo("sconosciuto"), "sconosciuto")


class TestFromCSV(unittest.TestCase):

    def test_load_sample_csv(self):
        sample_path = os.path.join(
            os.path.dirname(__file__), '..', 'sample_data', 'sample_voti.csv'
        )
        if not os.path.exists(sample_path):
            self.skipTest("sample_voti.csv non trovato")
        client = ClasseVivaClient()
        data = client.from_csv(sample_path)
        self.assertIn("voti", data)
        self.assertIn("student", data)
        self.assertGreater(len(data["voti"]), 0)

    def test_load_csv_not_found(self):
        client = ClasseVivaClient()
        with self.assertRaises(FileNotFoundError):
            client.from_csv("/nonexistent/path/voti.csv")

    def test_load_csv_invalid_values_skipped(self):
        """Righe con valore non numerico devono essere saltate."""
        content = (
            "studente_id,studente_nome,classe,materia,periodo,data,tipo,valore,note\n"
            "S1,Test,4A,Mate,1,2024-10-01,scritto,7.5,\n"
            "S1,Test,4A,Mate,1,2024-10-02,scritto,N/A,invalido\n"
            "S1,Test,4A,Mate,1,2024-10-03,orale,8.0,\n"
        )
        tmp_path = "/tmp/test_voti_invalid.csv"
        with open(tmp_path, "w") as f:
            f.write(content)
        client = ClasseVivaClient()
        data = client.from_csv(tmp_path)
        self.assertEqual(len(data["voti"]), 2)


# ── Test calcolo medie (app.py) ───────────────────────────────────────────────

class TestCalcoloMedie(unittest.TestCase):
    """Testa _calcola_medie direttamente importando da app."""

    def setUp(self):
        # Import lazy per evitare side effects
        import app as app_module
        self._calcola_medie = app_module._calcola_medie

    def test_media_aritmetica_semplice(self):
        voti = [
            {"materia": "Matematica", "tipo": "scritto", "valore": 6.0, "periodo": 1},
            {"materia": "Matematica", "tipo": "orale",   "valore": 8.0, "periodo": 1},
        ]
        medie = self._calcola_medie(voti, mode="arithmetic")
        self.assertAlmostEqual(medie["Matematica"]["p1"], 7.0)
        self.assertIsNone(medie["Matematica"]["p2"])
        self.assertAlmostEqual(medie["Matematica"]["media"], 7.0)

    def test_media_con_entrambi_periodi(self):
        voti = [
            {"materia": "Italiano", "tipo": "orale", "valore": 6.0, "periodo": 1},
            {"materia": "Italiano", "tipo": "orale", "valore": 8.0, "periodo": 2},
        ]
        medie = self._calcola_medie(voti, mode="arithmetic")
        self.assertAlmostEqual(medie["Italiano"]["p1"], 6.0)
        self.assertAlmostEqual(medie["Italiano"]["p2"], 8.0)
        self.assertAlmostEqual(medie["Italiano"]["media"], 7.0)

    def test_media_solo_secondo_periodo(self):
        voti = [
            {"materia": "Fisica", "tipo": "verifica", "valore": 7.5, "periodo": 2},
        ]
        medie = self._calcola_medie(voti, mode="arithmetic")
        self.assertIsNone(medie["Fisica"]["p1"])
        self.assertAlmostEqual(medie["Fisica"]["p2"], 7.5)
        self.assertAlmostEqual(medie["Fisica"]["media"], 7.5)

    def test_media_pesata(self):
        voti = [
            {"materia": "Matematica", "tipo": "scritto", "valore": 6.0, "periodo": 1},
            {"materia": "Matematica", "tipo": "orale",   "valore": 9.0, "periodo": 1},
        ]
        pesi = {"scritto": 70, "orale": 30}
        medie = self._calcola_medie(voti, mode="weighted", pesi=pesi)
        # media scritti = 6.0, media orali = 9.0
        # pesata = (6.0*0.7 + 9.0*0.3) / (0.7 + 0.3) = (4.2 + 2.7) / 1.0 = 6.9
        self.assertAlmostEqual(medie["Matematica"]["p1"], 6.9, places=5)

    def test_zero_voti(self):
        medie = self._calcola_medie([], mode="arithmetic")
        self.assertEqual(medie, {})

    def test_materie_multiple(self):
        voti = [
            {"materia": "Matematica", "tipo": "scritto", "valore": 8.0, "periodo": 1},
            {"materia": "Italiano",   "tipo": "orale",   "valore": 7.0, "periodo": 1},
            {"materia": "Fisica",     "tipo": "verifica","valore": 6.0, "periodo": 2},
        ]
        medie = self._calcola_medie(voti)
        self.assertIn("Matematica", medie)
        self.assertIn("Italiano", medie)
        self.assertIn("Fisica", medie)
        self.assertEqual(len(medie), 3)


if __name__ == '__main__':
    unittest.main(verbosity=2)
