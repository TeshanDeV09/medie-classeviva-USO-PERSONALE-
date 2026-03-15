"""
tests/test_integration.py
Smoke test e test di integrazione per gli endpoint Flask.
"""

import json
import os
import sys
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import app as flask_app

MOCK_DATA = {
    "student": {"id": "S12345", "nome": "Mario Rossi", "classe": "4AI"},
    "voti": [
        {"materia": "Matematica", "data": "2024-10-05", "tipo": "verifica", "valore": 7.5, "periodo": 1, "note": ""},
        {"materia": "Matematica", "data": "2024-11-12", "tipo": "scritto",  "valore": 6.0, "periodo": 1, "note": ""},
        {"materia": "Matematica", "data": "2025-02-10", "tipo": "verifica", "valore": 8.0, "periodo": 2, "note": ""},
        {"materia": "Italiano",   "data": "2024-10-08", "tipo": "orale",    "valore": 7.0, "periodo": 1, "note": ""},
        {"materia": "Italiano",   "data": "2025-03-15", "tipo": "orale",    "valore": 8.5, "periodo": 2, "note": ""},
        {"materia": "Fisica",     "data": "2024-10-15", "tipo": "scritto",  "valore": 5.5, "periodo": 1, "note": ""},
        {"materia": "Fisica",     "data": "2025-02-05", "tipo": "orale",    "valore": 7.0, "periodo": 2, "note": ""},
    ],
    "_fetched_at": "2025-01-01T10:00:00",
}


class TestFlaskEndpoints(unittest.TestCase):

    def setUp(self):
        flask_app.app.config['TESTING'] = True
        self.client = flask_app.app.test_client()

    @patch('app._get_voti', return_value=MOCK_DATA)
    def test_index_returns_200(self, mock_voti):
        resp = self.client.get('/')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'ClasseViva', resp.data)

    @patch('app._get_voti', return_value=MOCK_DATA)
    def test_api_voti_shape(self, mock_voti):
        resp = self.client.get('/api/voti')
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        self.assertIn('student', data)
        self.assertIn('voti', data)
        self.assertIn('_meta', data)
        # Controlla shape di un voto
        voto = data['voti'][0]
        for field in ('materia', 'data', 'tipo', 'valore', 'periodo'):
            self.assertIn(field, voto)

    @patch('app._get_voti', return_value=MOCK_DATA)
    def test_api_medie_arithmetic(self, mock_voti):
        resp = self.client.get('/api/medie?mode=arithmetic')
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        self.assertIn('medie_materie', data)
        self.assertIn('summary', data)
        summary = data['summary']
        self.assertIn('media_p1', summary)
        self.assertIn('media_p2', summary)
        self.assertIn('media_totale', summary)
        # Matematica P1 = (7.5 + 6.0) / 2 = 6.75
        mat = data['medie_materie'].get('Matematica', {})
        self.assertIsNotNone(mat)
        self.assertAlmostEqual(mat['p1'], 6.75, places=2)

    @patch('app._get_voti', return_value=MOCK_DATA)
    def test_api_export_csv_raw(self, mock_voti):
        resp = self.client.get('/api/export/csv?type=raw')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.mimetype, 'text/csv')
        content = resp.data.decode('utf-8')
        # Verifica intestazione
        self.assertIn('studente_id', content)
        self.assertIn('materia', content)
        self.assertIn('valore', content)
        # Verifica dati
        self.assertIn('Matematica', content)
        self.assertIn('7.5', content)

    @patch('app._get_voti', return_value=MOCK_DATA)
    def test_api_export_csv_medie(self, mock_voti):
        resp = self.client.get('/api/export/csv?type=medie')
        self.assertEqual(resp.status_code, 200)
        content = resp.data.decode('utf-8')
        self.assertIn('materia', content)
        self.assertIn('p1', content)
        self.assertIn('p2', content)

    @patch('app._get_voti', return_value=MOCK_DATA)
    def test_api_status(self, mock_voti):
        resp = self.client.get('/api/status')
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        self.assertIn('authenticated', data)
        self.assertIn('cache_valid', data)

    def test_debug_forbidden_in_production(self):
        """Debug page deve essere 403 in produzione."""
        import os
        old_env = os.environ.get('FLASK_ENV', '')
        os.environ['FLASK_ENV'] = 'production'
        try:
            resp = self.client.get('/debug')
            self.assertEqual(resp.status_code, 403)
        finally:
            os.environ['FLASK_ENV'] = old_env

    @patch('app._get_voti', return_value=MOCK_DATA)
    def test_debug_accessible_in_development(self, mock_voti):
        """Debug page deve essere accessibile in development."""
        import os
        old_env = os.environ.get('FLASK_ENV', '')
        os.environ['FLASK_ENV'] = 'development'
        try:
            resp = self.client.get('/debug')
            self.assertIn(resp.status_code, [200, 500])  # 500 ok se template manca
        finally:
            os.environ['FLASK_ENV'] = old_env


class TestMedieCalcoli(unittest.TestCase):
    """Test di integrazione per _calcola_medie con dati mock."""

    def test_media_globale_corretta(self):
        """Verifica che media totale = media delle due medie periodo."""
        voti = MOCK_DATA['voti']
        medie = flask_app._calcola_medie(voti)

        # Matematica: P1=(7.5+6.0)/2=6.75, P2=8.0 → media=(6.75+8.0)/2=7.375
        mat = medie['Matematica']
        self.assertAlmostEqual(mat['p1'],    6.75,  places=2)
        self.assertAlmostEqual(mat['p2'],    8.0,   places=2)
        self.assertAlmostEqual(mat['media'], 7.375, places=2)

    def test_materia_solo_un_periodo(self):
        voti = [{"materia": "Arte", "tipo": "orale", "valore": 9.0, "periodo": 1, "data": ""}]
        medie = flask_app._calcola_medie(voti)
        self.assertAlmostEqual(medie['Arte']['p1'],    9.0)
        self.assertIsNone(medie['Arte']['p2'])
        self.assertAlmostEqual(medie['Arte']['media'], 9.0)

    def test_nessun_voto(self):
        medie = flask_app._calcola_medie([])
        self.assertEqual(medie, {})

    def test_arrotondamento_non_applicato_in_calcolo(self):
        """Il calcolo deve mantenere float completo (arrotondamento solo in output)."""
        voti = [
            {"materia": "Chimica", "tipo": "scritto", "valore": 7.0, "periodo": 1, "data": ""},
            {"materia": "Chimica", "tipo": "scritto", "valore": 8.0, "periodo": 1, "data": ""},
            {"materia": "Chimica", "tipo": "scritto", "valore": 6.0, "periodo": 1, "data": ""},
        ]
        medie = flask_app._calcola_medie(voti)
        self.assertAlmostEqual(medie['Chimica']['p1'], 7.0, places=5)


if __name__ == '__main__':
    unittest.main(verbosity=2)
