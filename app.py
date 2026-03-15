"""
app.py  —  ClasseViva Dashboard locale
USO STRETTAMENTE PERSONALE. Nessun dato viene inviato a server esterni.
"""

import csv
import io
import json
import logging
import os
from datetime import datetime

from flask import Flask, jsonify, render_template, request, Response, abort
from dotenv import load_dotenv

from classeviva_client import (
    ClasseVivaClient,
    AuthError,
    NetworkError,
    ThrottleError,
    ClasseVivaError,
)

load_dotenv()

app = Flask(__name__)
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-secret-change-me")

logger = logging.getLogger("app")

# ── Client singleton ──────────────────────────────────────────────────────────
client = ClasseVivaClient()
client.invalidate_cache()

# ── Percorso CSV sample (fallback automatico se API non disponibile) ───────────
SAMPLE_CSV = os.path.join(os.path.dirname(__file__), "sample_data", "sample_voti.csv")


def _get_voti(force_refresh: bool = False) -> dict:
    """
    Tenta di ottenere i voti dall'API.
    In caso di errore, prova il fallback con il CSV di sample.
    """
    try:
        return client.fetch_voti(force_refresh=force_refresh)
    except AuthError as e:
        logger.warning(f"Errore auth, provo fallback CSV: {e}")
    except (NetworkError, ClasseVivaError) as e:
        logger.warning(f"Errore API, provo fallback CSV: {e}")

    # Fallback CSV
    if os.path.exists(SAMPLE_CSV):
        logger.info("Usando sample_data/sample_voti.csv come fallback.")
        return client.from_csv(SAMPLE_CSV)

    raise ClasseVivaError(
        "API non raggiungibile e nessun CSV di fallback trovato. "
        "Inserisci le credenziali in .env oppure carica sample_data/sample_voti.csv."
    )


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    from flask import make_response
    resp = make_response(render_template("index.html"))
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    resp.headers['Pragma'] = 'no-cache'
    return resp


@app.route("/debug")
def debug():
    if os.getenv("FLASK_ENV") != "development":
        abort(403, "Pagina debug disponibile solo in FLASK_ENV=development")
    try:
        data = _get_voti()
    except ClasseVivaError as e:
        data = {"error": str(e)}
    return render_template("debug.html", data=json.dumps(data, indent=2, ensure_ascii=False))


@app.route("/api/voti")
def api_voti():
    try:
        data = _get_voti()
        # Aggiungi metadati utili al frontend
        data["_meta"] = {
            "server_time": datetime.now().isoformat(),
            "cache_age_seconds": client.get_cache_age_seconds(),
            "source": data.get("_source", "api"),
        }
        return jsonify(data)
    except ThrottleError as e:
        return jsonify({"error": str(e), "type": "throttle"}), 429
    except AuthError as e:
        return jsonify({"error": str(e), "type": "auth"}), 401
    except (NetworkError, ClasseVivaError) as e:
        return jsonify({"error": str(e), "type": "network"}), 503


@app.route("/api/refresh", methods=["POST"])
def api_refresh():
    try:
        data = _get_voti(force_refresh=True)
        return jsonify({
            "success": True,
            "message": "Dati aggiornati.",
            "fetched_at": data.get("_fetched_at"),
            "voti_count": len(data.get("voti", [])),
        })
    except ThrottleError as e:
        return jsonify({"success": False, "error": str(e), "type": "throttle"}), 429
    except ClasseVivaError as e:
        return jsonify({"success": False, "error": str(e), "type": "error"}), 503


@app.route("/api/export/csv")
def api_export_csv():
    export_type = request.args.get("type", "raw")  # "raw" o "medie"
    try:
        data = _get_voti()
    except ClasseVivaError as e:
        return jsonify({"error": str(e)}), 503

    student = data.get("student", {})
    voti = data.get("voti", [])

    output = io.StringIO()

    if export_type == "medie":
        # CSV delle medie per materia
        writer = csv.writer(output)
        writer.writerow(["materia", "p1", "p2", "media_generale", "n_voti_p1", "n_voti_p2"])
        medie = _calcola_medie(voti, mode="arithmetic")
        for materia, m in sorted(medie.items()):
            writer.writerow([
                materia,
                f"{m['p1']:.2f}" if m["p1"] is not None else "",
                f"{m['p2']:.2f}" if m["p2"] is not None else "",
                f"{m['media']:.2f}" if m["media"] is not None else "",
                m["n_p1"],
                m["n_p2"],
            ])
        filename = "medie_classeviva.csv"
    else:
        # CSV voti grezzi
        writer = csv.writer(output)
        writer.writerow([
            "studente_id", "studente_nome", "classe",
            "materia", "periodo", "data", "tipo", "valore", "note"
        ])
        for v in voti:
            writer.writerow([
                student.get("id", ""),
                student.get("nome", ""),
                student.get("classe", ""),
                v.get("materia", ""),
                v.get("periodo", ""),
                v.get("data", ""),
                v.get("tipo", ""),
                v.get("valore", ""),
                v.get("note", ""),
            ])
        filename = "voti_classeviva.csv"

    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.route("/api/status")
def api_status():
    return jsonify(client.status())


@app.route("/api/upload_csv", methods=["POST"])
def api_upload_csv():
    """Endpoint per caricare un CSV manuale come override."""
    if "file" not in request.files:
        return jsonify({"error": "Nessun file inviato"}), 400
    file = request.files["file"]
    if not file.filename.endswith(".csv"):
        return jsonify({"error": "Il file deve essere un CSV"}), 400

    # Salva temporaneamente
    temp_path = os.path.join("/tmp", "uploaded_voti.csv")
    file.save(temp_path)
    try:
        data = client.from_csv(temp_path)
        return jsonify({
            "success": True,
            "voti_count": len(data.get("voti", [])),
            "student": data.get("student"),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 400


# ── Calcolo medie (helper backend) ───────────────────────────────────────────

def _calcola_medie(voti: list, mode: str = "arithmetic", pesi: dict = None) -> dict:
    """
    Calcola medie per materia per periodo.
    mode: "arithmetic" | "weighted"
    pesi: dict tipo→percentuale (somma 100), usato solo in weighted mode.
    """
    from collections import defaultdict

    # Raggruppa: materia → periodo → lista voti (solo voti numerici)
    grouped = defaultdict(lambda: defaultdict(list))
    for v in voti:
        if v.get("valore") is None:
            continue  # salta voti in lettere (es. religione)
        grouped[v["materia"]][v["periodo"]].append(v)

    risultati = {}

    for materia, periodi in grouped.items():
        def calc_media(lista_voti):
            if not lista_voti:
                return None, 0
            if mode == "weighted" and pesi:
                # Raggruppa per tipo
                per_tipo = defaultdict(list)
                for v in lista_voti:
                    per_tipo[v["tipo"]].append(v["valore"])
                media_per_tipo = {}
                for tipo, vals in per_tipo.items():
                    media_per_tipo[tipo] = sum(vals) / len(vals)
                # Media pesata
                total_peso = 0
                somma = 0
                for tipo, media in media_per_tipo.items():
                    peso = pesi.get(tipo, 0) / 100.0
                    somma += media * peso
                    total_peso += peso
                if total_peso == 0:
                    # Fallback aritmetica
                    vals_all = [v["valore"] for v in lista_voti]
                    return sum(vals_all) / len(vals_all), len(vals_all)
                return somma / total_peso, len(lista_voti)
            else:
                vals = [v["valore"] for v in lista_voti]
                return sum(vals) / len(vals), len(vals)

        m_p1, n_p1 = calc_media(periodi.get(1, []))
        m_p2, n_p2 = calc_media(periodi.get(2, []))

        # Media generale: media delle due medie di periodo (se entrambe disponibili)
        if m_p1 is not None and m_p2 is not None:
            media_gen = (m_p1 + m_p2) / 2
        elif m_p1 is not None:
            media_gen = m_p1
        elif m_p2 is not None:
            media_gen = m_p2
        else:
            media_gen = None

        risultati[materia] = {
            "p1": m_p1,
            "p2": m_p2,
            "media": media_gen,
            "n_p1": n_p1,
            "n_p2": n_p2,
        }

    return risultati


@app.route("/api/medie")
def api_medie():
    """Ritorna le medie calcolate (aritmetiche o pesate)."""
    mode = request.args.get("mode", "arithmetic")
    pesi_raw = request.args.get("pesi", None)
    pesi = None
    if pesi_raw:
        try:
            pesi = json.loads(pesi_raw)
        except (json.JSONDecodeError, ValueError):
            return jsonify({"error": "Formato pesi non valido (atteso JSON)"}), 400

    try:
        data = _get_voti()
    except ClasseVivaError as e:
        return jsonify({"error": str(e)}), 503

    voti = data.get("voti", [])
    medie = _calcola_medie(voti, mode=mode, pesi=pesi)

    # Medie globali per periodo
    tutti_p1 = [v["valore"] for v in voti if v["periodo"] == 1 and v.get("valore") is not None]
    tutti_p2 = [v["valore"] for v in voti if v["periodo"] == 2 and v.get("valore") is not None]

    media_globale_p1 = sum(tutti_p1) / len(tutti_p1) if tutti_p1 else None
    media_globale_p2 = sum(tutti_p2) / len(tutti_p2) if tutti_p2 else None

    if media_globale_p1 and media_globale_p2:
        media_totale = (media_globale_p1 + media_globale_p2) / 2
    elif media_globale_p1:
        media_totale = media_globale_p1
    elif media_globale_p2:
        media_totale = media_globale_p2
    else:
        media_totale = None

    return jsonify({
        "mode": mode,
        "medie_materie": medie,
        "summary": {
            "media_p1": round(media_globale_p1, 2) if media_globale_p1 else None,
            "media_p2": round(media_globale_p2, 2) if media_globale_p2 else None,
            "media_totale": round(media_totale, 2) if media_totale else None,
        },
    })


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=5000,
        debug=os.getenv("FLASK_ENV") == "development",
    )
