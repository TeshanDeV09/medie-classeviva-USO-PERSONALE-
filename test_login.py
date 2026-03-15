"""
test_login.py — script di debug per isolare il problema di login.
Esegui con: python test_login.py
"""
import json
import os
import requests
from dotenv import load_dotenv

load_dotenv()

USERNAME = os.getenv("CLASSEVIVA_USER", "")
PASSWORD = os.getenv("CLASSEVIVA_PASS", "")

print(f"Username: {USERNAME[:4]}**** (lunghezza: {len(USERNAME)})")
print(f"Password: {'*'*len(PASSWORD)} (lunghezza: {len(PASSWORD)})")
print()

# ── Tentativo 1: esatto come il PHP che funziona ─────────────────────────────
print("=" * 60)
print("Tentativo 1: header identici al PHP funzionante")
print("=" * 60)

url = "https://web.spaggiari.eu/rest/v1/auth/login"
payload = {"ident": None, "pass": PASSWORD, "uid": USERNAME}

headers = {
    "Content-Type": "application/json",
    "Z-Dev-ApiKey":  "+zorro+",
    "User-Agent":    "zorro/1.0",
}

print(f"URL: {url}")
print(f"Headers: {headers}")
print(f"Payload: {json.dumps({**payload, 'pass': '***'})}")
print()

try:
    r = requests.post(url, json=payload, headers=headers, timeout=10)
    print(f"Status: {r.status_code}")
    print(f"Response headers: {dict(r.headers)}")
    try:
        print(f"Body: {json.dumps(r.json(), indent=2)}")
    except Exception:
        print(f"Body (raw): {r.text[:500]}")
except Exception as e:
    print(f"Errore: {e}")

print()

# ── Tentativo 2: con session (per vedere se cambia qualcosa) ─────────────────
print("=" * 60)
print("Tentativo 2: con requests.Session()")
print("=" * 60)

session = requests.Session()
session.headers.clear()  # rimuovi tutti gli header di default
session.headers.update(headers)

try:
    r2 = session.post(url, json=payload, timeout=10)
    print(f"Status: {r2.status_code}")
    try:
        print(f"Body: {json.dumps(r2.json(), indent=2)}")
    except Exception:
        print(f"Body (raw): {r2.text[:500]}")
except Exception as e:
    print(f"Errore: {e}")

print()

# ── Tentativo 3: controlla cosa vede effettivamente il server ────────────────
print("=" * 60)
print("Tentativo 3: dump esatto della richiesta che viene inviata")
print("=" * 60)

# Usa PreparedRequest per vedere gli header esatti
req = requests.Request("POST", url, json=payload, headers=headers)
prepared = req.prepare()
print("Header esatti inviati da Python:")
for k, v in prepared.headers.items():
    print(f"  {k}: {v}")
print(f"Body: {prepared.body}")
