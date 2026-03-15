# 📊 ClasseViva Dashboard

> Dashboard locale per visualizzare i tuoi voti ClasseViva con grafici interattivi, medie per periodo e per materia, esportazione CSV e supporto dark/light.

**⚠️ USO STRETTAMENTE PERSONALE** — Nessun dato viene inviato a server esterni. Tutto rimane in locale su `127.0.0.1`.

---

## Screenshot

La dashboard mostra:
- **Cards riepilogative** (Media P1 / P2 / Totale) con codice colore (verde ≥7, giallo ≥5.5, rosso <5.5)
- **Tabella materie** ordinabile con P1, P2, media e conteggio voti
- **Grafico lineare** interattivo: andamento nel tempo, filtrabile per materia
- **Grafico a barre** comparativo P1 vs P2 per materia
- **Voti recenti** in pill card
- **Modalità pesata**: assegna pesi % a scritti, orali, pratici

---

## Prerequisiti

- Python 3.10+
- pip
- Accesso a ClasseViva (credenziali del registro elettronico Spaggiari)

---

## Setup

### 1. Clona il repo

```bash
git clone https://github.com/tuonome/classeviva-web.git
cd classeviva-web
```

### 2. Crea virtualenv e installa dipendenze

```bash
python -m venv venv
source venv/bin/activate          # macOS / Linux
# oppure: venv\Scripts\activate   # Windows

pip install -r requirements.txt
```

### 3. Configura le credenziali

```bash
cp .env.example .env
```

Modifica `.env` con le tue credenziali:

```env
CLASSEVIVA_USER=tuo_codice_fiscale
CLASSEVIVA_PASS=tua_password
FLASK_ENV=development
FLASK_SECRET_KEY=una-chiave-segreta-random
CACHE_TTL=300
THROTTLE_SECONDS=30
```

> **🔒 Non committare mai il file `.env`!** È incluso nel `.gitignore`.

### 4. Avvia l'app

```bash
python app.py
```

Apri il browser su: **http://127.0.0.1:5000**

---

## Test con dati di esempio (senza credenziali)

Se non hai credenziali o vuoi testare offline, l'app usa automaticamente il file `sample_data/sample_voti.csv` come fallback.

Puoi anche caricare il tuo CSV dalla UI (pulsante "Seleziona file" nel banner upload).

**Formato CSV richiesto:**
```csv
studente_id,studente_nome,classe,materia,periodo,data,tipo,valore,note
S001,Mario Rossi,4AI,Matematica,1,2024-10-05,verifica,7.5,
```

---

## Eseguire i test

```bash
# Tutti i test
pytest tests/ -v

# Solo unit test backend
pytest tests/test_backend.py -v

# Solo integration test
pytest tests/test_integration.py -v

# Con coverage
pytest tests/ --cov=. --cov-report=html
```

---

## Endpoints API

| Endpoint | Metodo | Descrizione |
|---|---|---|
| `/` | GET | Dashboard principale |
| `/api/voti` | GET | JSON con tutti i voti |
| `/api/medie` | GET | Medie per materia (`?mode=arithmetic\|weighted&pesi={...}`) |
| `/api/refresh` | POST | Forza aggiornamento da ClasseViva (throttled: max 1/30s) |
| `/api/export/csv` | GET | Download CSV voti raw (`?type=raw`) o medie (`?type=medie`) |
| `/api/status` | GET | Stato cache e autenticazione |
| `/api/upload_csv` | POST | Carica CSV manuale |
| `/debug` | GET | Debug JSON (solo `FLASK_ENV=development`) |

---

## Struttura progetto

```
classeviva-web/
├── app.py                   # Flask app + endpoints + logica medie
├── classeviva_client.py     # Wrapper API + caching + throttle + fallback CSV
├── requirements.txt
├── .env.example             # Template credenziali (NON committare .env)
├── .gitignore
├── README.md
├── templates/
│   ├── index.html           # Dashboard principale
│   └── debug.html           # Pagina debug (solo dev)
├── static/
│   ├── css/style.css        # Design tokens, dark/light, responsive
│   └── js/main.js           # Fetch API, Chart.js, interattività
├── tests/
│   ├── test_backend.py      # Unit test: client, cache, throttle, medie
│   └── test_integration.py  # Integration test: endpoint Flask, CSV export
├── sample_data/
│   └── sample_voti.csv      # Dati di esempio per test offline
└── logs/
    └── app.log              # Log applicazione (gitignored)
```

---

## Funzionalità

### Modalità calcolo medie
- **Aritmetica semplice**: `media = sum(voti) / n`
- **Pesata**: assegna pesi % per tipo (scritto/orale/pratico). Calcola la media per tipo, poi media pesata. La somma dei pesi deve essere 100%.

### Logica media generale
- Se esiste P1 e P2: `media = (mp1 + mp2) / 2`
- Se esiste solo P1: `media = mp1` (documentato nell'UI)
- Se esiste solo P2: `media = mp2`

### Caching e throttle
- I dati vengono messi in cache per 300 secondi (configurabile via `CACHE_TTL`)
- Il refresh manuale è limitato a una richiesta ogni 30 secondi (`THROTTLE_SECONDS`)
- Backoff esponenziale su errori di rete (3 tentativi)

---

## Sicurezza

- Le credenziali restano **solo** nel file `.env` locale, mai nel codice o nel repo
- Nessuna richiesta a server terzi diversi da `web.spaggiari.eu`
- La pagina `/debug` è accessibile solo con `FLASK_ENV=development`
- L'app ascolta solo su `127.0.0.1` (non esposta sulla rete locale)

---

## Docker (opzionale)

```dockerfile
# Dockerfile — solo per sviluppo locale, NON pubblicare con credenziali!
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
EXPOSE 5000
CMD ["python", "app.py"]
```

```bash
docker build -t classeviva-dashboard .
docker run --env-file .env -p 5000:5000 classeviva-dashboard
```

---

## Note legali

Questo progetto è per **uso strettamente personale**. Non redistribuire. Rispetta i [Termini di Servizio di ClasseViva/Spaggiari](https://web.spaggiari.eu).

---

## Versione

`v1.0.0` — Python 3.10+ / Flask 2.3+ / Chart.js 4.4
