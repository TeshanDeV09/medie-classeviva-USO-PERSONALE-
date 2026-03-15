"""
classeviva_client.py
Scraper del portale web.spaggiari.eu — simula un browser normale.
Usa l'endpoint AuthApi4.php scoperto tramite analisi del traffico di rete.
USO STRETTAMENTE PERSONALE.
"""

import csv
import logging
import os
import re
import time
from datetime import datetime
from functools import wraps
from typing import Dict, Optional

import requests
from dotenv import load_dotenv

load_dotenv()

# -- Logging ------------------------------------------------------------------
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler("logs/app.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("classeviva_client")

# -- Costanti -----------------------------------------------------------------
BASE_WEB  = "https://web.spaggiari.eu"
BASE_REST = "https://web.spaggiari.eu/rest/v1"

LOGIN_URL = f"{BASE_WEB}/auth-p7/app/default/AuthApi4.php?a=aLoginPwd"

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept":          "application/json, text/plain, */*",
    "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection":      "keep-alive",
    "Origin":          "https://web.spaggiari.eu",
    "Referer":         "https://web.spaggiari.eu/home/app/default/login.php",
}

# -- Eccezioni ----------------------------------------------------------------
class ClasseVivaError(Exception): pass
class AuthError(ClasseVivaError):  pass
class NetworkError(ClasseVivaError): pass
class ThrottleError(ClasseVivaError): pass


# -- Retry decorator ----------------------------------------------------------
def retry(max_attempts: int = 3, delay: float = 2.0, backoff: float = 2.0):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            attempt, wait = 0, delay
            while attempt < max_attempts:
                try:
                    return func(*args, **kwargs)
                except (requests.RequestException, NetworkError) as e:
                    attempt += 1
                    if attempt >= max_attempts:
                        raise
                    logger.warning(
                        f"{func.__name__} fallito ({attempt}/{max_attempts}): {e}. "
                        f"Riprovo in {wait:.1f}s..."
                    )
                    time.sleep(wait)
                    wait *= backoff
        return wrapper
    return decorator


# -- Client -------------------------------------------------------------------
class ClasseVivaClient:
    """
    Client ClasseViva che usa il portale web come un browser normale.
    Endpoint di login: AuthApi4.php?a=aLoginPwd
    """

    def __init__(self):
        self.username         = os.getenv("CLASSEVIVA_USER", "")
        self.password         = os.getenv("CLASSEVIVA_PASS", "")
        self.cache_ttl        = int(os.getenv("CACHE_TTL", "300"))
        self.throttle_seconds = int(os.getenv("THROTTLE_SECONDS", "30"))

        self._session         = self._new_session()
        self._student_id: Optional[str] = os.getenv("CLASSEVIVA_STUDENT_ID", "") or None
        self._logged_in       = False

        self._cache:        Optional[Dict] = None
        self._cache_time:   Optional[datetime] = None
        self._last_request: Optional[datetime] = None

    # -- Session --------------------------------------------------------------

    def _new_session(self) -> requests.Session:
        s = requests.Session()
        s.headers.update(BROWSER_HEADERS)
        return s

    # -- Throttle -------------------------------------------------------------

    def _check_throttle(self):
        if self._last_request:
            elapsed = (datetime.now() - self._last_request).total_seconds()
            if elapsed < self.throttle_seconds:
                raise ThrottleError(
                    f"Attendi {self.throttle_seconds - elapsed:.0f}s prima di aggiornare."
                )

    def _mark_request(self):
        self._last_request = datetime.now()

    # -- Cache ----------------------------------------------------------------

    def _is_cache_valid(self) -> bool:
        if not self._cache or not self._cache_time:
            return False
        return (datetime.now() - self._cache_time).total_seconds() < self.cache_ttl

    def _set_cache(self, data: Dict):
        self._cache      = data
        self._cache_time = datetime.now()
        logger.info("Cache aggiornata.")

    def get_cache_age_seconds(self) -> Optional[float]:
        if not self._cache_time:
            return None
        return (datetime.now() - self._cache_time).total_seconds()

    def invalidate_cache(self):
        self._cache = self._cache_time = None

    # -- Login ----------------------------------------------------------------

    @retry(max_attempts=3, delay=2.0)
    def login(self):
        if not self.username or not self.password:
            raise AuthError(
                "Credenziali mancanti. Imposta CLASSEVIVA_USER e CLASSEVIVA_PASS nel .env"
            )

        logger.info(f"Login per: {self.username[:4]}****")

        # Visita la home per ottenere cookie iniziali
        try:
            self._session.get(
                f"{BASE_WEB}/home/app/default/login.php",
                timeout=10
            )
        except requests.RequestException:
            pass

        # Payload JSON come da analisi del traffico
        payload = {
            "cid":        "",
            "uid":        self.username,
            "pwd":        self.password,
            "pin":        "",
            "target":     "",
            "logged":     "N",
            "wannalogon": "A",
        }

        try:
            resp = self._session.post(
                LOGIN_URL,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=15,
                allow_redirects=True,
            )
        except requests.RequestException as e:
            raise NetworkError(f"Errore di rete nel login: {e}") from e

        # Log risposta per debug
        try:
            body = resp.json()
        except Exception:
            body = resp.text[:500]
        logger.info(f"Login -> HTTP {resp.status_code}: {body}")

        if resp.status_code == 200:
            # Controlla se la risposta contiene un token o conferma di login
            if isinstance(body, dict):
                # Cerca token in vari formati possibili
                token = (
                    body.get("token") or
                    body.get("Token") or
                    body.get("authToken") or
                    (body.get("data") or {}).get("token")
                )
                if token:
                    self._session.headers.update({"Z-Auth-Token": token})
                    logger.info(f"Token ricevuto: {str(token)[:20]}...")

                # Cerca student ID e classe dalla risposta di login
                # La risposta ha struttura: data.auth.accountInfo.{type, id, cid}
                account_info = ((body.get("data") or {}).get("auth") or {}).get("accountInfo") or {}
                tipo_acc = account_info.get("type", "")
                id_acc   = account_info.get("id", "")
                cid_acc  = account_info.get("cid", "")  # es. "VRIT0007" = classe

                if tipo_acc and id_acc:
                    sid = f"{tipo_acc}{id_acc}"
                else:
                    sid = (
                        body.get("studentId") or
                        body.get("userId") or
                        body.get("UID") or
                        (body.get("data") or {}).get("studentId")
                    )
                if sid and not self._student_id:
                    self._student_id = str(sid)

                # Salva classe dal login (disponibile subito, senza dover fare altre richieste)
                if cid_acc and not getattr(self, "_classe_cache", None):
                    self._classe_cache = cid_acc
                    logger.info(f"Classe trovata dal login: {cid_acc}")

                # Controlla errori espliciti
                error = body.get("error") or body.get("Error") or body.get("message")
                if error and resp.status_code != 200:
                    raise AuthError(f"Login fallito: {error}")

        elif resp.status_code in (401, 403):
            raise AuthError(f"Credenziali non valide (HTTP {resp.status_code})")
        elif resp.status_code != 200:
            raise NetworkError(f"Errore HTTP {resp.status_code} nel login")

        # Se non abbiamo trovato l'ID, usa username
        if not self._student_id:
            self._student_id = self.username
            logger.warning(f"Student ID non trovato, uso username: {self._student_id}")

        self._logged_in = True
        logger.info(f"Login completato. Student ID: {self._student_id}")

    # -- Fetch voti -----------------------------------------------------------

    @retry(max_attempts=2, delay=3.0)
    def _fetch_grades_from_web(self) -> Dict:
        from selenium import webdriver
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.chrome.service import Service
        from webdriver_manager.chrome import ChromeDriverManager
        from bs4 import BeautifulSoup
        import re, time

        self._mark_request()
        logger.info("Avvio Chrome automatizzato...")

        options = webdriver.ChromeOptions()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--log-level=3")

        driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()),
            options=options
        )

        try:
            # Login
            driver.get(f"{BASE_WEB}/home/app/default/login.php")
            wait = WebDriverWait(driver, 15)
            time.sleep(2)

            uid_input = driver.find_element(By.CSS_SELECTOR, "input[name='uid'], #uid, input[type='text']")
            pwd_input = driver.find_element(By.CSS_SELECTOR, "input[name='pwd'], #pwd, input[type='password']")
            uid_input.clear()
            uid_input.send_keys(self.username)
            pwd_input.clear()
            pwd_input.send_keys(self.password)
            driver.find_element(By.CSS_SELECTOR, "button[type='submit'], input[type='submit'], .btn-accedi, #accedi").click()

            wait.until(lambda d: "login" not in d.current_url)
            logger.info(f"Login Selenium OK. URL: {driver.current_url}")

            # Estrai classe navigando alla pagina anagrafica studente
            if not getattr(self, "_classe_cache", None):
                try:
                    psrc = driver.page_source
                    msoup = BeautifulSoup(psrc, "html.parser")
                    for el in msoup.find_all(string=True):
                        t = str(el).strip()
                        if re.match(r"^[1-5][A-Z]{1,5}$", t) and 2 <= len(t) <= 6:
                            self._classe_cache = t
                            logger.info(f"Classe trovata dal menu: {t}")
                            break
                    if not getattr(self, "_classe_cache", None):
                        m_cls = re.search(r"(?:Classe|classe)[:\s]+([1-5]\s*[A-Z]{1,5})", psrc)
                        if m_cls:
                            self._classe_cache = m_cls.group(1).replace(" ", "")
                            logger.info(f"Classe trovata da pattern: {self._classe_cache}")
                    if not getattr(self, "_classe_cache", None):
                        # Naviga alla pagina registro lezioni che mostra la classe
                        driver.get(f"{BASE_WEB}/fml/app/default/regclasse_lezioni_xstudenti.php")
                        time.sleep(2)
                        psrc2 = driver.page_source
                        # Cerca classe in span.page_title_variable
                        # es. "3EI INFORMATICA E TELECOMUNICAZIONI..."
                        msoup2 = BeautifulSoup(psrc2, "html.parser")
                        ptv = msoup2.find("span", class_="page_title_variable")
                        if ptv:
                            testo_ptv = ptv.get_text(strip=True)
                            logger.info(f"page_title_variable: {testo_ptv[:60]}")
                            # Estrai prima parola formato NXX
                            m_cls2 = re.match(r"([1-5][A-Z]{1,5})", testo_ptv)
                            if m_cls2:
                                self._classe_cache = m_cls2.group(1).upper()
                                logger.info(f"Classe trovata: {self._classe_cache}")
                except Exception as e:
                    logger.warning(f"Errore estrazione classe: {e}")

            # Naviga ai voti
            driver.get(f"{BASE_WEB}/cvv/app/default/genitori_voti.php?filtro=tutto")
            time.sleep(6)  # attendi JS asincrono

            soup = BeautifulSoup(driver.page_source, "html.parser")

            voti = []
            materia_corrente = "Sconosciuta"

            # Parser: i voti sono nelle righe riga_materia_componente
            # Ogni TR ha attributi materia_id e sessione (S1=P1, S3=P2)
            for tr in soup.find_all("tr", class_="riga_materia_componente"):
                materia_el = tr.find(class_="materia_desc")
                if not materia_el:
                    continue
                materia = materia_el.get_text(strip=True).title()
                sessione = tr.get("sessione", "S1")
                periodo = 1 if sessione == "S1" else 2

                for td in tr.find_all("td", class_=re.compile(r"cella_voto")):
                    p_voto = td.find("p", class_=re.compile(r"s_reg_testo"))
                    if not p_voto:
                        continue
                    testo = p_voto.get_text(strip=True)
                    if not testo:
                        continue

                    # Normalizza il testo del voto
                    testo_norm = testo.replace("\u00bd", ".5")  # ½ -> .5

                    # Data — formato dd/mm -> anno corretto (calcolata prima del check lettera)
                    data_el = td.find(class_=re.compile(r"voto_data"))
                    data_str = data_el.get_text(strip=True) if data_el else ""
                    # Rimuovi caratteri non-numerici che a volte si attaccano alla data (es "17/11b")
                    data_clean = re.sub(r"[^0-9/]", "", data_str)
                    try:
                        parts = data_clean.split("/")
                        if len(parts) == 2:
                            import datetime as dt
                            mese = int(parts[1])
                            anno_corrente = dt.date.today().year
                            if periodo == 1 and mese >= 9:
                                anno = anno_corrente - 1 if dt.date.today().month < 9 else anno_corrente
                            else:
                                anno = anno_corrente
                            data_str = f"{anno}-{parts[1].zfill(2)}-{parts[0].zfill(2)}"
                    except Exception:
                        pass

                    # Tipo dal title del div
                    div_voto = td.find("div", title=True)
                    tipo_raw = div_voto.get("title", "").lower() if div_voto else ""
                    tipo = self._normalize_tipo(tipo_raw)

                    # Voti in lettere (religione): b=buono, ds=distinto, o=ottimo, s=sufficiente
                    VOTI_LETTERA = {"nc", "ns", "b", "s", "ds", "o", "mb", "i", "ab"}
                    # Voti blu = f_reg_voto_dettaglio -> non entrano nella media
                    is_dettaglio = bool(td.find("div", class_=re.compile(r"f_reg_voto_dettaglio")))

                    if testo_norm.lower() in VOTI_LETTERA:
                        voti.append({
                            "materia": materia,
                            "data":    data_str,
                            "tipo":    tipo,
                            "valore":  None,
                            "valore_lettera": testo_norm.upper(),
                            "periodo": periodo,
                            "note":    "voto in lettere",
                            "non_fa_media": False,
                        })
                        continue

                    # Voto in frazione (es. "38/48") -> converti in /10
                    if "/" in testo_norm:
                        try:
                            num, den = testo_norm.split("/")
                            valore_float = round(float(num) / float(den) * 10, 2)
                        except Exception:
                            continue
                    else:
                        # Gestisci + e - (es. "8-"=7.75, "7+"=7.25)
                        mod = 0.25 if testo_norm.endswith("+") else (-0.25 if testo_norm.endswith("-") else 0.0)
                        valore_raw = re.sub(r"[+\-]+$", "", testo_norm).strip()
                        try:
                            valore_float = float(valore_raw.replace(",", ".")) + mod
                        except ValueError:
                            continue

                    voti.append({
                        "materia": materia,
                        "data":    data_str,
                        "tipo":    tipo,
                        "valore":  valore_float,
                        "periodo": periodo,
                        "note":    "non fa media" if is_dettaglio else "",
                        "non_fa_media": is_dettaglio,
                    })
            logger.info(f"Estratti {len(voti)} voti tramite Selenium.")

            # Nome studente dalla pagina
            nome = self.username
            nome_el = soup.find(class_="page_title_variable")
            if nome_el:
                nome = nome_el.get_text(strip=True).title()
            elif soup.find(class_="name"):
                nome = soup.find(class_="name").get_text(strip=True).title()

            # Classe: usa _classe_cache impostata durante la navigazione
            classe = getattr(self, "_classe_cache", "N/A") or "N/A"

            return {
                "student": {
                    "id":     self._student_id or "N/A",
                    "nome":   nome,
                    "classe": classe,
                },
                "voti":        voti,
                "_fetched_at": datetime.now().isoformat(),
                "_source":     "selenium",
            }

            return {
                "student": {
                    "id":     self._student_id or "N/A",
                    "nome":   nome,
                    "classe": classe,
                },
                "voti":        voti,
                "_fetched_at": datetime.now().isoformat(),
                "_source":     "selenium",
            }

        finally:
            driver.quit()

    # -- Normalizzazione ------------------------------------------------------

    def _normalize_grades(self, raw: Dict) -> Dict:
        grades_raw   = raw.get("grades", [])
        student_info = raw.get("studentInfo", {})

        voti = []
        for g in grades_raw:
            valore = g.get("decimalValue") or g.get("displayValue")
            try:
                valore_float = float(str(valore).replace(",", ".").strip())
            except (ValueError, TypeError):
                logger.warning(f"Voto non numerico ignorato: {valore!r}")
                continue

            tipo_raw = (g.get("componentDesc") or "").lower()
            tipo     = self._normalize_tipo(tipo_raw)

            periodo = g.get("periodPos") or g.get("periodCode") or 1
            try:
                periodo = int(periodo)
            except (ValueError, TypeError):
                periodo = 1

            voti.append({
                "materia": g.get("subjectDesc", "Sconosciuta"),
                "data":    g.get("evtDate", ""),
                "tipo":    tipo,
                "valore":  valore_float,
                "periodo": periodo,
                "note":    g.get("notesForFamily", ""),
            })

        nome = (
            student_info.get("name", "") + " " + student_info.get("surname", "")
        ).strip() or self.username

        return {
            "student": {
                "id":     self._student_id or "N/A",
                "nome":   nome,
                "classe": student_info.get("className", "N/A"),
            },
            "voti":        voti,
            "_fetched_at": datetime.now().isoformat(),
        }

    @staticmethod
    def _normalize_tipo(tipo_raw: str) -> str:
        if any(k in tipo_raw for k in ["scritto", "written", "compit"]):
            return "scritto"
        if any(k in tipo_raw for k in ["oral", "orale"]):
            return "orale"
        if any(k in tipo_raw for k in ["pratico", "practic", "lab"]):
            return "pratico"
        if any(k in tipo_raw for k in ["verifica", "test", "quiz"]):
            return "verifica"
        return tipo_raw or "altro"

    # -- Fetch pubblico (con cache) -------------------------------------------

    def fetch_voti(self, force_refresh: bool = False) -> Dict:
        if not force_refresh and self._is_cache_valid():
            logger.info("Dati serviti dalla cache.")
            return self._cache

        if force_refresh:
            self._check_throttle()

        data = self._fetch_grades_from_web()
        self._set_cache(data)
        return data

    # -- Fallback CSV ---------------------------------------------------------

    def from_csv(self, path: str) -> Dict:
        logger.info(f"Caricamento voti da CSV: {path}")
        if not os.path.exists(path):
            raise FileNotFoundError(f"CSV non trovato: {path}")

        voti = []
        student_info = {"id": "CSV", "nome": "Da CSV", "classe": "N/A"}

        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for i, row in enumerate(reader):
                if i == 0:
                    student_info = {
                        "id":     row.get("studente_id",   "CSV"),
                        "nome":   row.get("studente_nome", "Da CSV"),
                        "classe": row.get("classe",        "N/A"),
                    }
                try:
                    valore = float(str(row.get("valore", "0")).replace(",", "."))
                except ValueError:
                    logger.warning(f"Riga {i+1}: valore non valido, ignorata.")
                    continue
                try:
                    periodo = int(row.get("periodo", "1"))
                except ValueError:
                    periodo = 1

                voti.append({
                    "materia": row.get("materia", "Sconosciuta"),
                    "data":    row.get("data",    ""),
                    "tipo":    row.get("tipo",    "altro"),
                    "valore":  valore,
                    "periodo": periodo,
                    "note":    row.get("note",    ""),
                })

        data = {
            "student":     student_info,
            "voti":        voti,
            "_fetched_at": datetime.now().isoformat(),
            "_source":     "csv",
        }
        self._set_cache(data)
        logger.info(f"Caricati {len(voti)} voti dal CSV.")
        return data

    # -- Status ---------------------------------------------------------------

    def status(self) -> Dict:
        return {
            "authenticated":     self._logged_in,
            "student_id":        self._student_id,
            "cache_valid":       self._is_cache_valid(),
            "cache_age_seconds": self.get_cache_age_seconds(),
            "last_request":      (
                self._last_request.isoformat() if self._last_request else None
            ),
        }
