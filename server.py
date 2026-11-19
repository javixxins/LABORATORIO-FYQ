# -*- coding: utf-8 -*-
"""
Laboratorio FyQ - Control de stock y viabilidad de prácticas
Servidor local (Flask + SQLite). Solo escucha en 127.0.0.1.
"""
import io
import json
import math
import os
import re
import sqlite3
import sys
import time
import unicodedata
import uuid
from datetime import datetime

_LIB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if os.path.isdir(_LIB) and _LIB not in sys.path:
    sys.path.insert(0, _LIB)  # librerías incluidas en la versión instalable

from flask import Flask, jsonify, request, send_from_directory, abort, g

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.environ.get("LABFYQ_DATA") or os.path.join(BASE, "datos")
UPLOADS = os.path.join(DATA, "guiones")
DB_PATH = os.path.join(DATA, "laboratorio.db")
STATIC = os.path.join(BASE, "static")
APP_ID = "laboratorio-fyq"

os.makedirs(UPLOADS, exist_ok=True)

app = Flask(__name__, static_folder=None)
app.config["MAX_CONTENT_LENGTH"] = 40 * 1024 * 1024


# ----------------------------------------------------------------- base de datos
def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    d = g.pop("db", None)
    if d is not None:
        d.close()


SCHEMA = """
CREATE TABLE IF NOT EXISTS config (clave TEXT PRIMARY KEY, valor TEXT);
CREATE TABLE IF NOT EXISTS categorias (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  nombre TEXT UNIQUE NOT NULL,
  color TEXT DEFAULT '#14b8a6',
  consumible INTEGER DEFAULT 0,
  orden INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  nombre TEXT NOT NULL,
  categoria_id INTEGER REFERENCES categorias(id) ON DELETE SET NULL,
  unidad TEXT DEFAULT 'uds',
  cantidad REAL DEFAULT 0,
  rotos REAL DEFAULT 0,
  minimo REAL DEFAULT 0,
  ubicacion TEXT DEFAULT '',
  notas TEXT DEFAULT '',
  alias TEXT DEFAULT '',
  creado TEXT
);
CREATE TABLE IF NOT EXISTS movimientos (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  item_id INTEGER,
  item_nombre TEXT,
  tipo TEXT,
  cantidad REAL,
  unidad TEXT,
  nota TEXT,
  fecha TEXT
);
CREATE TABLE IF NOT EXISTS grupos (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  curso TEXT,
  grupo TEXT,
  alumnos INTEGER DEFAULT 20,
  agrupamiento INTEGER DEFAULT 2,
  lista TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS practicas (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  titulo TEXT,
  pdf_file TEXT,
  pdf_nombre TEXT,
  texto TEXT,
  materiales TEXT,
  creado TEXT,
  ultima TEXT,
  ajustes TEXT DEFAULT '{}'
);
"""

DEFAULT_CONFIG = {
    "instituto": "Mi Instituto",
    "departamento": "Departamento de Física y Química",
    "laboratorio": "Laboratorio de Física y Química",
    "capacidad": "30",
    "mesas": "8",
    "sillas": "30",
    "alumnos_por_mesa": "4",
    "mesas_por_fila": "4",
    "margen": "10",
    "logo": "",
}

DEFAULT_CATS = [
    ("RECIPIENTES", "#0ea5e9", 0),
    ("REACTIVOS", "#f59e0b", 1),
    ("INSTRUMENTOS", "#8b5cf6", 0),
    ("OTROS", "#64748b", 0),
]


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def init_db():
    con = sqlite3.connect(DB_PATH)
    con.executescript(SCHEMA)
    for k, v in DEFAULT_CONFIG.items():
        con.execute("INSERT OR IGNORE INTO config(clave, valor) VALUES (?,?)", (k, v))
    if con.execute("SELECT COUNT(*) FROM categorias").fetchone()[0] == 0:
        for i, (n, c, cons) in enumerate(DEFAULT_CATS):
            con.execute("INSERT INTO categorias(nombre,color,consumible,orden) VALUES (?,?,?,?)", (n, c, cons, i))
    if con.execute("SELECT COUNT(*) FROM grupos").fetchone()[0] == 0:
        con.execute("INSERT INTO grupos(curso,grupo,alumnos,agrupamiento) VALUES ('3º ESO','A',24,2)")
    cols = [r[1] for r in con.execute("PRAGMA table_info(grupos)")]
    if "lista" not in cols:
        con.execute("ALTER TABLE grupos ADD COLUMN lista TEXT DEFAULT ''")
    if "ajustes" not in [r[1] for r in con.execute("PRAGMA table_info(practicas)")]:
        con.execute("ALTER TABLE practicas ADD COLUMN ajustes TEXT DEFAULT '{}'")
    con.commit()
    con.close()


def rows(cur):
    return [dict(r) for r in cur.fetchall()]


def get_config():
    return {r["clave"]: r["valor"] for r in db().execute("SELECT clave, valor FROM config")}


def num(v, default=0.0):
    try:
        if isinstance(v, str):
            v = v.replace(",", ".").strip()
        return float(v)
    except (TypeError, ValueError):
        return default


# ----------------------------------------------------------------- normalización
STOP = {"de", "del", "la", "el", "los", "las", "y", "e", "en", "con", "para", "por", "un", "una",
        "unos", "unas", "al", "a", "o", "u", "su", "sus", "aprox", "aproximadamente", "cada"}

UNIT_MAP = {
    "ml": "mL", "mls": "mL", "cm3": "mL", "cc": "mL", "cm³": "mL", "mililitro": "mL", "mililitros": "mL",
    "l": "L", "litro": "L", "litros": "L", "dl": "dL", "cl": "cL",
    "g": "g", "gr": "g", "grs": "g", "gramo": "g", "gramos": "g",
    "mg": "mg", "miligramo": "mg", "miligramos": "mg",
    "kg": "kg", "kilo": "kg", "kilos": "kg", "kilogramo": "kg", "kilogramos": "kg",
    "gota": "gotas", "gotas": "gotas",
    "ud": "uds", "uds": "uds", "u": "uds", "unidad": "uds", "unidades": "uds", "pieza": "uds", "piezas": "uds",
    "m": "m", "cm": "cm", "metro": "m", "metros": "m",
    "pastilla": "uds", "pastillas": "uds", "trozo": "uds", "trozos": "uds", "hoja": "uds", "hojas": "uds",
    "cucharadita": "cucharaditas", "cucharaditas": "cucharaditas", "pizca": "pizcas", "pizcas": "pizcas",
}
FAMILY = {
    "mL": ("vol", 1.0), "L": ("vol", 1000.0), "dL": ("vol", 100.0), "cL": ("vol", 10.0),
    "gotas": ("vol", 0.05),
    "g": ("mass", 1.0), "mg": ("mass", 0.001), "kg": ("mass", 1000.0),
    "m": ("len", 1.0), "cm": ("len", 0.01),
}
UNIT_RE = (r"(?:ml|mls|cm3|cm³|cc|mililitros?|litros?|l|dl|cl|gramos?|grs?|g|mg|miligramos?|kg|kilos?|"
           r"kilogramos?|gotas?|uds?|u|unidad(?:es)?|piezas?|pastillas?|trozos?|hojas?|metros?|m|cm|"
           r"cucharaditas?|pizcas?)")

NUM_WORDS = {"un": 1, "uno": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6,
             "siete": 7, "ocho": 8, "nueve": 9, "diez": 10, "once": 11, "doce": 12, "veinte": 20}

CONTAINER_WORDS = ("vaso", "probeta", "matraz", "bureta", "pipeta", "erlenmeyer", "tubo", "frasco", "bote",
                   "cristalizador", "embudo", "balon", "botella", "jeringa", "cubeta", "recipiente",
                   "vidrio", "capsula", "crisol", "aforado", "kitasato", "decantacion", "termometro",
                   "dinamometro", "muelle", "pesa", "regla", "cuentagotas", "gradilla", "placa", "petri")


def strip_accents(s):
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def norm_unit(u):
    if not u:
        return "uds"
    k = strip_accents(u.strip().lower()).rstrip(".")
    return UNIT_MAP.get(k, u.strip())


def singular(w):
    if len(w) <= 3 or not w.endswith("s") or w[-2].isdigit():
        return w
    if w.endswith("ces"):
        return w[:-3] + "z"
    if w.endswith("iones"):
        return w[:-5] + "ion"
    if w.endswith("es") and len(w) > 4 and w[-3] in "rlndj":
        return w[:-2]
    return w[:-1]


def tokens(s):
    s = strip_accents((s or "").lower())
    s = s.replace("³", "3")
    # une número + unidad: "250 ml" -> "250ml", "0,1 m" -> "0.1m"
    s = re.sub(r"(\d)[,](\d)", r"\1.\2", s)
    s = re.sub(r"(\d+(?:\.\d+)?)\s*(ml|cm3|cc|l|g|mg|kg|m|cm|mm|n|v|w|mol/l|%)\b", r"\1\2", s)
    s = s.replace("cm3", "ml").replace("cc", "ml")
    parts = re.findall(r"[a-z0-9ñ.%/]+", s)
    out = []
    for p in parts:
        p = p.strip(".")
        if not p or p in STOP:
            continue
        out.append(singular(p))
    return out


def similarity(a, b):
    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        return 0.0
    if " ".join(ta) == " ".join(tb):
        return 1.0
    sa, sb = set(ta), set(tb)
    words_a = {t for t in sa if not re.match(r"^\d", t)}
    words_b = {t for t in sb if not re.match(r"^\d", t)}
    nums_a = sa - words_a
    nums_b = sb - words_b

    def tok_eq(x, y):
        if x == y:
            return True
        if len(x) >= 5 and len(y) >= 5 and (x.startswith(y) or y.startswith(x)):
            return True
        return False

    inter = 0.0
    for x in words_a:
        if any(tok_eq(x, y) for y in words_b):
            inter += 1
    if not words_a or not words_b:
        return 0.0
    score = 2 * inter / (len(words_a) + len(words_b))
    # la primera palabra (sustantivo principal) pesa más
    wa = [t for t in ta if t in words_a]
    wb = [t for t in tb if t in words_b]
    if wa and wb and tok_eq(wa[0], wb[0]):
        score += 0.15
    sobra_a = [x for x in words_a if not any(tok_eq(x, y) for y in words_b)]
    sobra_b = [y for y in words_b if not any(tok_eq(x, y) for x in words_a)]
    if sobra_a and sobra_b:
        score -= 0.2  # ambos tienen palabras distintivas diferentes (p. ej. pipeta Pasteur / pipeta graduada)
    if nums_a and nums_b:
        score += 0.25 if (nums_a & nums_b) else -0.35
    elif nums_b and not nums_a:
        score -= 0.05
    return max(0.0, min(1.0, score))


def match_item(nombre, items):
    best, best_s = None, 0.0
    key = " ".join(tokens(nombre))
    for it in items:
        aliases = [a for a in (it.get("alias") or "").split("|") if a.strip()]
        for al in aliases:
            if " ".join(tokens(al)) == key:
                return it, 1.0
        s = similarity(nombre, it["nombre"])
        for al in aliases:
            s = max(s, similarity(nombre, al))
        if s > best_s:
            best, best_s = it, s
    if best_s >= 0.5:
        return best, best_s
    return None, best_s


# ----------------------------------------------------------------- lectura del guion
SECTION_START = re.compile(
    r"^\s*(?:[\dIVX]+\s*[\.\)\-]\s*)?(?:lista\s+de\s+)?(material(?:es)?|reactivos?|equipos?|instrumental|"
    r"productos(?:\s+qu[ií]micos)?|sustancias|utensilios|aparatos)\b(.*)$", re.I)
SECTION_END = re.compile(
    r"^\s*(?:[\dIVX]+\s*[\.\)\-]\s*)?(procedimiento|desarrollo|m[eé]todo|metodolog[ií]a|fundamento|"
    r"introducci[oó]n|objetivos?|cuestiones|preguntas|resultados|conclusi[oó]n|conclusiones|observaciones|"
    r"precauciones|seguridad|montaje|realizaci[oó]n|experiencia|actividad(?:es)?|anexo|bibliograf[ií]a|"
    r"normas|c[aá]lculos|toma\s+de\s+datos|pasos|modo\s+de\s+operar|t[eé]cnica|marco\s+te[oó]rico|"
    r"teor[ií]a|evaluaci[oó]n|informe|hip[oó]tesis|tabla|datos|limpieza|residuos)\b", re.I)
BULLET = re.compile(r"^\s*(?:[•·▪◦●○■□►➢➤✓✔\-–—\*]|o\s|\d{1,2}[\.\)]\s|[a-h]\)\s)\s*")


def extract_pdf_text(path):
    try:
        from pypdf import PdfReader
    except ImportError:
        return ""
    try:
        reader = PdfReader(path)
        out = []
        for page in reader.pages:
            try:
                out.append(page.extract_text() or "")
            except Exception:
                pass
        return "\n".join(out)
    except Exception:
        return ""


def guess_title(text):
    lines = [x.strip() for x in text.splitlines()]
    for i, l in enumerate(lines):
        if len(l) < 4:
            continue
        if re.match(r"^(ies|i\.e\.s|colegio|instituto|departamento|nombre|curso|fecha|grupo)\b", l, re.I):
            continue
        if i + 1 < len(lines) and lines[i + 1][:1].islower():
            l = l + " " + lines[i + 1]
        return l[:140]
    return "Práctica sin título"


def split_items(line):
    # separa por ; o por comas seguidas de letra (no decimales 0,1)
    parts = re.split(r";|,\s+(?=[A-Za-zÁÉÍÓÚáéíóúÑñ])|\s+[-–]\s+(?=[A-ZÁÉÍÓÚ])|\s+[ye]\s+(?=\d|[A-Za-zÁÉÍÓÚáéíóúÑñ]{3})",
                     line)
    return [p.strip() for p in parts if p and p.strip()]


def find_material_lines(text):
    lines = [l.rstrip() for l in text.splitlines()]
    collected = []
    inside = False
    scope = None
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        m = SECTION_START.match(line)
        if m and (len(line) < 70 or ":" in line[:40]):
            inside = True
            rest = m.group(2) or ""
            rest = re.sub(r"^\s*(?:y\s+reactivos|y\s+material|necesarios?|empleados?|utilizados?|"
                          r"de\s+laboratorio|requeridos?|a\s+utilizar)?\s*", "", rest, flags=re.I)
            rest = rest.lstrip(":.- ").strip()
            sc, rest2 = detect_scope(rest)
            scope = sc
            rest2 = rest2.lstrip(":.- ").strip()
            if rest2:
                collected.append((rest2, True, scope))
            continue
        if inside and SECTION_END.match(line) and len(line) < 80:
            inside = False
            continue
        if inside:
            has_bullet = bool(BULLET.match(line))
            collected.append((line, has_bullet, scope))
    # une líneas partidas (continuaciones que empiezan en minúscula sin viñeta)
    merged = []
    for line, has_b, sc in collected:
        if merged and not has_b and line[:1].islower() and not re.match(r"^\d", line):
            merged[-1] = (merged[-1][0] + " " + line, merged[-1][1])
        else:
            merged.append((BULLET.sub("", line).strip(), sc))
    items = []
    for l, sc in merged:
        # la anotación de ámbito de la línea completa se aplica a todas sus partes
        lsc, l = detect_scope(l)
        for p in split_items(l):
            p = p.strip(" .:-–")
            if 2 < len(p) < 140:
                items.append((p, lsc or sc))
    return items


def detect_scope(s):
    t = strip_accents(s.lower())
    scope = None
    if re.search(r"\bpor\s+alumno|\bcada\s+alumno|\bpor\s+persona|\bindividual", t):
        scope = "alumno"
    elif re.search(r"\bpor\s+(grupo|pareja|equipo|mesa)|\bcada\s+(grupo|pareja)", t):
        scope = "grupo"
    elif re.search(r"\(?\b(profesor|comun(?:es)?|toda\s+la\s+clase|para\s+la\s+clase|en\s+total|mesa\s+del\s+profesor)\b\)?", t):
        scope = "total"
    cleaned = re.sub(r"\(?\s*(por\s+(grupo|pareja|equipo|mesa|alumno|persona)|cada\s+(grupo|pareja|alumno)|"
                     r"para\s+(el\s+)?profesor|del\s+profesor|com[uú]n(es)?|para\s+toda\s+la\s+clase|"
                     r"en\s+total|individual)\s*\)?", "", s, flags=re.I)
    return scope, cleaned.strip(" ,.;:-")


def parse_item(s, default_scope=None):
    original = s
    scope, s = detect_scope(s)
    scope = scope or default_scope or "grupo"
    s = s.strip()
    qty, unit = None, None
    name = s
    n_re = r"(\d+(?:[.,]\d+)?)"
    is_container = any(w in strip_accents(s.lower()) for w in CONTAINER_WORDS)

    m = re.match(r"^" + n_re + r"\s*(?:x|×)?\s*(" + UNIT_RE + r")?\.?\s+(?:de\s+)?(.+)$", s, re.I)
    if m:
        qty = num(m.group(1))
        unit = norm_unit(m.group(2)) if m.group(2) else "uds"
        name = m.group(3)
    else:
        m = re.match(r"^(un|uno|una|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|once|doce|veinte)\s+(.+)$", s, re.I)
        if m:
            qty = NUM_WORDS[m.group(1).lower()]
            unit = "uds"
            name = m.group(2)
    if qty is None:
        # cantidad al final: "Sulfato de cobre: 5 g", "Tubos de ensayo (x6)", "Pinzas x 2"
        m = re.match(r"^(.+?)\s*(?:[:=]|\(|\s[x×]|\s[-–])\s*[x×]?\s*" + n_re + r"\s*(" + UNIT_RE + r")?\.?\s*\)?$", s, re.I)
        if m:
            u = norm_unit(m.group(3)) if m.group(3) else "uds"
            if is_container and u in ("mL", "L"):
                pass  # es la capacidad del recipiente, forma parte del nombre
            else:
                qty = num(m.group(2))
                unit = u
                name = m.group(1)
    if qty is None:
        # "Agua destilada 100 mL" (no recipiente) -> cantidad final con unidad de masa/volumen
        m = re.match(r"^(.+?)\s+" + n_re + r"\s*(" + UNIT_RE + r")\.?$", s, re.I)
        if m and not is_container and norm_unit(m.group(3)) in ("mL", "L", "g", "mg", "kg", "gotas"):
            qty = num(m.group(2))
            unit = norm_unit(m.group(3))
            name = m.group(1)
    if qty is None:
        qty, unit = 1.0, "uds"
    name = re.sub(r"\s+", " ", name).strip(" ,.;:-()")
    if name:
        name = name[0].upper() + name[1:]
    return {"texto": original, "nombre": name or original, "cantidad": qty, "unidad": unit, "ambito": scope}


def analyze_text(text, items):
    lines = find_material_lines(text)
    out = []
    for l, sc in lines:
        p = parse_item(l, sc)
        it, score = match_item(p["nombre"], items)
        p["item_id"] = it["id"] if it else None
        p["confianza"] = round(score, 2)
        p["ignorar"] = False
        out.append(p)
    return out


# ----------------------------------------------------------------- viabilidad
def unit_factor(from_u, to_u):
    """factor para pasar una cantidad en from_u a to_u. None si no son compatibles."""
    fu, tu = norm_unit(from_u), norm_unit(to_u)
    if fu == tu:
        return 1.0
    a, b = FAMILY.get(fu), FAMILY.get(tu)
    if a and b and a[0] == b[0]:
        return a[1] / b[1]
    return None


def fmt(x):
    if x is None:
        return ""
    if abs(x - round(x)) < 1e-9:
        return str(int(round(x)))
    return ("%.2f" % x).rstrip("0").rstrip(".")


NOMBRE_GRUPO = {1: "alumno", 2: "pareja", 3: "trío", 4: "grupo de 4"}


def distribuir(n, t):
    """Reparte n alumnos en grupos de tamaño t. El resto se reparte añadiendo un alumno
    a algunos grupos (p. ej. 25 alumnos por parejas -> 11 parejas + 1 grupo de 3)."""
    n, t = int(n), max(1, int(t))
    if n <= 0:
        return []
    if t == 1:
        return [1] * n
    if n <= t:
        return [n]
    if t == 2:
        # parejas; si es impar, la última pareja pasa a ser un grupo de 3
        sizes = [2] * (n // 2)
        if n % 2:
            sizes[-1] += 1
        return sizes
    # grupos de t (3 o 4): tantos grupos como hagan falta, de t y t-1 alumnos (sin superar t)
    g = int(math.ceil(n / float(t)))
    base, extra = divmod(n, g)
    return [base + 1] * extra + [base] * (g - extra)


def nombre_tamano(s, plural=False):
    base = NOMBRE_GRUPO.get(s, "grupo de %d" % s)
    if not plural:
        return base
    return {"alumno": "alumnos", "pareja": "parejas", "trío": "tríos"}.get(base, base.replace("grupo", "grupos"))


def describir_reparto(sizes):
    if not sizes:
        return "Sin alumnos"
    cuenta = {}
    for s in sizes:
        cuenta[s] = cuenta.get(s, 0) + 1
    partes = []
    for s in sorted(cuenta, key=lambda k: -cuenta[k]):
        c = cuenta[s]
        if s == 1:
            partes.append("%d alumno%s individual%s" % (c, "s" if c > 1 else "", "es" if c > 1 else ""))
        elif s == 3 and c == 1:
            partes.append("1 grupo de 3")
        else:
            partes.append("%d %s" % (c, nombre_tamano(s, c > 1)))
    return " + ".join(partes)


def _demanda(materiales, items, avisos):
    """Agrega la demanda por artículo del stock: por grupo, por alumno y fija (profesor)."""
    agg, sin_stock = {}, []
    for m in materiales:
        if m.get("ignorar"):
            continue
        q = num(m.get("cantidad"), 1)
        amb = m.get("ambito") or "grupo"
        iid = m.get("item_id")
        try:
            iid = int(iid) if iid not in (None, "", "null") else None
        except (TypeError, ValueError):
            iid = None
        if iid is None or iid not in items:
            sin_stock.append({"nombre": m.get("nombre"), "q": q, "ambito": amb, "unidad": m.get("unidad") or "uds"})
            continue
        it = items[iid]
        f = unit_factor(m.get("unidad") or "uds", it["unidad"])
        if f is None:
            f = 1.0
            avisos.append("«%s»: la unidad del guion (%s) no coincide con la del stock (%s); se compara el número tal cual."
                          % (m.get("nombre"), m.get("unidad"), it["unidad"]))
        a = agg.setdefault(iid, {"g": 0.0, "s": 0.0, "f": 0.0, "lineas": []})
        a[{"total": "f", "alumno": "s"}.get(amb, "g")] += q * f
        a["lineas"].append(m.get("nombre"))
    return agg, sin_stock


def _need(a, n_alumnos, n_grupos, mult, discreto):
    v = (a["g"] * n_grupos + a["s"] * n_alumnos + a["f"]) * mult
    return math.ceil(v - 1e-9) if discreto else v


def compute_viability(materiales, alumnos, tam, cfg):
    con = db()
    items = {r["id"]: dict(r) for r in con.execute(
        "SELECT i.*, c.nombre AS categoria, c.consumible FROM items i LEFT JOIN categorias c ON c.id=i.categoria_id")}
    margen = num(cfg.get("margen"), 10)
    alumnos = max(1, int(alumnos))
    tam = max(1, int(tam))
    reparto = distribuir(alumnos, tam)
    grupos = len(reparto)
    avisos = []
    agg, sin_stock = _demanda(materiales, items, avisos)

    def mult_of(it):
        return 1.0 if norm_unit(it["unidad"]) == "uds" else 1 + margen / 100.0

    # espacio del laboratorio
    cap = int(num(cfg.get("capacidad"), 0))
    sillas = int(num(cfg.get("sillas"), 0))
    mesas = int(num(cfg.get("mesas"), 0))
    apm = int(num(cfg.get("alumnos_por_mesa"), 4)) or 1
    espacio = []
    if cap > 0 and alumnos > cap:
        espacio.append("El grupo tiene %d alumnos y la capacidad del laboratorio es de %d." % (alumnos, cap))
    if sillas > 0 and alumnos > sillas:
        espacio.append("Faltan sillas: hay %d y se necesitan %d (faltan %d)." % (sillas, alumnos, alumnos - sillas))
    plano, sin_puesto = asignar_mesas(reparto, mesas, apm)
    if mesas > 0 and sin_puesto:
        espacio.append("Faltan mesas: %d puesto%s de trabajo no cabe%s en las %d mesas (%d alumnos por mesa)."
                       % (len(sin_puesto), "s" if len(sin_puesto) > 1 else "", "n" if len(sin_puesto) > 1 else "",
                          mesas, apm))

    def cabe(n):
        """¿Hay material y espacio para n alumnos?"""
        if n <= 0:
            return True
        if sin_stock:
            return False
        rp = distribuir(n, tam)
        ng = len(rp)
        if (cap > 0 and n > cap) or (sillas > 0 and n > sillas) or (mesas > 0 and asignar_mesas(rp, mesas, apm)[1]):
            return False
        for iid, a in agg.items():
            it = items[iid]
            if _need(a, n, ng, mult_of(it), norm_unit(it["unidad"]) == "uds") > float(it["cantidad"] or 0) + 1e-9:
                return False
        return True

    max_alumnos = 0
    for n in range(alumnos, 0, -1):
        if cabe(n):
            max_alumnos = n
            break

    lineas = []
    for iid, a in agg.items():
        it = items[iid]
        discreto = norm_unit(it["unidad"]) == "uds"
        need = _need(a, alumnos, grupos, mult_of(it), discreto)
        disp = float(it["cantidad"] or 0)
        falta = max(0.0, need - disp)
        lineas.append({
            "item_id": iid, "nombre": it["nombre"],
            "guion": ", ".join(x for x in a["lineas"] if x),
            "categoria": it.get("categoria") or "Sin categoría",
            "consumible": bool(it.get("consumible")),
            "unidad": it["unidad"],
            "por_grupo": round(a["g"], 3), "por_alumno": round(a["s"], 3), "fijo": round(a["f"], 3),
            "necesario": round(need, 3), "disponible": round(disp, 3),
            "rotos": float(it["rotos"] or 0), "falta": round(falta, 3), "ok": falta <= 1e-9,
            "margen": (not discreto) and margen > 0,
        })
    for s in sin_stock:
        need = s["q"] if s["ambito"] == "total" else (s["q"] * alumnos if s["ambito"] == "alumno" else s["q"] * grupos)
        lineas.append({
            "item_id": None, "nombre": s["nombre"], "guion": s["nombre"], "categoria": "No registrado en stock",
            "consumible": False, "unidad": s["unidad"],
            "por_grupo": s["q"] if s["ambito"] == "grupo" else 0, "por_alumno": s["q"] if s["ambito"] == "alumno" else 0,
            "fijo": s["q"] if s["ambito"] == "total" else 0,
            "necesario": need, "disponible": 0, "rotos": 0, "falta": need, "ok": False, "sin_stock": True, "margen": False,
        })

    faltas = [l for l in lineas if not l["ok"]]
    viable = not faltas and not espacio and len(lineas) > 0
    lineas.sort(key=lambda l: (l["ok"], l["categoria"], l["nombre"]))
    reparto_max = distribuir(max_alumnos, tam)
    return {
        "viable": viable,
        "alumnos": alumnos,
        "agrupamiento": tam,
        "nombre_agrupamiento": nombre_tamano(tam, True),
        "grupos": grupos,
        "reparto": reparto,
        "reparto_texto": describir_reparto(reparto),
        "max_alumnos": max_alumnos,
        "max_grupos": len(reparto_max),
        "reparto_max_texto": describir_reparto(reparto_max),
        "lineas": lineas,
        "faltas": faltas,
        "espacio": espacio,
        "avisos": avisos,
        "margen": margen,
        "mesas": mesas, "alumnos_por_mesa": apm,
        "plano": plano, "sin_puesto": sin_puesto,
        "sin_material": len(lineas) == 0,
    }


def asignar_mesas(reparto, mesas, apm):
    """Coloca cada puesto de trabajo (grupo) en una mesa (primer hueco libre).
    Devuelve (lista de mesas con los índices de grupo, índices sin puesto)."""
    if mesas <= 0:
        return [], []
    libres = [apm] * mesas
    plano = [[] for _ in range(mesas)]
    sin = []
    for i, s in enumerate(reparto):
        for m in range(mesas):
            if libres[m] >= s or (not plano[m] and s > apm):
                plano[m].append(i)
                libres[m] -= s
                break
        else:
            sin.append(i)
    return plano, sin


def parse_lista(txt):
    out = []
    for line in (txt or "").replace("\r", "\n").split("\n"):
        l = line.strip().strip(";,\t ")
        l = re.sub(r"^\d+[\.\)\-\s]+", "", l).strip()
        if l and not re.match(r"^(nombre|alumno|apellidos?)\b.*$", l, re.I):
            # "Apellidos, Nombre" -> "Nombre Apellidos"
            if l.count(",") == 1:
                a, b = [x.strip() for x in l.split(",")]
                if a and b:
                    l = b + " " + a
            out.append(re.sub(r"\s+", " ", l))
    return out


def equipos(nombres, reparto, aleatorio=False):
    nombres = list(nombres)
    if aleatorio:
        import random
        random.shuffle(nombres)
    out, k = [], 0
    for s in reparto:
        grupo = []
        for _ in range(s):
            grupo.append(nombres[k] if k < len(nombres) else "Alumno %d" % (k + 1))
            k += 1
        out.append(grupo)
    return out


def kit_para(lineas, size):
    """Material que recibe un grupo de 'size' alumnos."""
    out = []
    for l in lineas:
        q = l["por_grupo"] + l["por_alumno"] * size
        if q > 0:
            out.append((l["nombre"], q, l["unidad"]))
    return out


# ----------------------------------------------------------------- rutas estáticas
@app.route("/")
def index():
    return send_from_directory(STATIC, "index.html")


@app.route("/static/<path:p>")
def static_files(p):
    resp = send_from_directory(STATIC, p)
    resp.headers["Cache-Control"] = "no-cache"
    return resp


@app.route("/logo")
def logo():
    f = get_config().get("logo")
    if not f or not os.path.exists(os.path.join(DATA, f)):
        return send_from_directory(STATIC, "icono.svg")
    return send_from_directory(DATA, f)


@app.route("/api/ping")
def ping():
    return jsonify({"app": APP_ID, "ok": True, "datos": DATA})


# ----------------------------------------------------------------- configuración
@app.route("/api/config", methods=["GET", "PUT"])
def config_api():
    con = db()
    if request.method == "PUT":
        data = request.get_json(force=True) or {}
        for k in DEFAULT_CONFIG:
            if k in data and k != "logo":
                con.execute("INSERT OR REPLACE INTO config(clave, valor) VALUES (?,?)", (k, str(data[k])))
        con.commit()
    return jsonify(get_config())


@app.route("/api/config/logo", methods=["POST", "DELETE"])
def logo_api():
    con = db()
    old = get_config().get("logo")
    if old and os.path.exists(os.path.join(DATA, old)):
        try:
            os.remove(os.path.join(DATA, old))
        except OSError:
            pass
    if request.method == "DELETE":
        con.execute("UPDATE config SET valor='' WHERE clave='logo'")
        con.commit()
        return jsonify({"ok": True})
    f = request.files.get("logo")
    if not f:
        abort(400)
    ext = os.path.splitext(f.filename or "")[1].lower()
    if ext not in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"):
        return jsonify({"error": "Formato de imagen no admitido"}), 400
    name = "logo_%d%s" % (int(time.time()), ext)
    f.save(os.path.join(DATA, name))
    con.execute("INSERT OR REPLACE INTO config(clave, valor) VALUES ('logo', ?)", (name,))
    con.commit()
    return jsonify({"ok": True, "logo": name})


# ----------------------------------------------------------------- categorías
@app.route("/api/categorias", methods=["GET", "POST"])
def categorias():
    con = db()
    if request.method == "POST":
        d = request.get_json(force=True) or {}
        nombre = (d.get("nombre") or "").strip().upper()
        if not nombre:
            return jsonify({"error": "Falta el nombre"}), 400
        try:
            orden = con.execute("SELECT COALESCE(MAX(orden),0)+1 FROM categorias").fetchone()[0]
            con.execute("INSERT INTO categorias(nombre,color,consumible,orden) VALUES (?,?,?,?)",
                        (nombre, d.get("color") or "#14b8a6", 1 if d.get("consumible") else 0, orden))
            con.commit()
        except sqlite3.IntegrityError:
            return jsonify({"error": "Ya existe una categoría con ese nombre"}), 400
    return jsonify(rows(con.execute(
        "SELECT c.*, (SELECT COUNT(*) FROM items i WHERE i.categoria_id=c.id) AS n FROM categorias c ORDER BY orden, id")))


@app.route("/api/categorias/<int:cid>", methods=["PUT", "DELETE"])
def categoria(cid):
    con = db()
    if request.method == "DELETE":
        n = con.execute("SELECT COUNT(*) FROM items WHERE categoria_id=?", (cid,)).fetchone()[0]
        if n:
            return jsonify({"error": "La categoría tiene %d materiales. Muévelos antes de borrarla." % n}), 400
        con.execute("DELETE FROM categorias WHERE id=?", (cid,))
    else:
        d = request.get_json(force=True) or {}
        try:
            con.execute("UPDATE categorias SET nombre=?, color=?, consumible=? WHERE id=?",
                        ((d.get("nombre") or "").strip().upper(), d.get("color") or "#14b8a6",
                         1 if d.get("consumible") else 0, cid))
        except sqlite3.IntegrityError:
            return jsonify({"error": "Ya existe una categoría con ese nombre"}), 400
    con.commit()
    return jsonify({"ok": True})


# ----------------------------------------------------------------- materiales
def log_mov(con, item, tipo, cantidad, nota=""):
    con.execute("INSERT INTO movimientos(item_id,item_nombre,tipo,cantidad,unidad,nota,fecha) VALUES (?,?,?,?,?,?,?)",
                (item["id"], item["nombre"], tipo, cantidad, item["unidad"], nota, now()))


ITEM_SQL = ("SELECT i.*, c.nombre AS categoria, c.color AS color, c.consumible AS consumible "
            "FROM items i LEFT JOIN categorias c ON c.id=i.categoria_id")


@app.route("/api/items", methods=["GET", "POST"])
def items_api():
    con = db()
    if request.method == "POST":
        d = request.get_json(force=True) or {}
        nombre = (d.get("nombre") or "").strip()
        if not nombre:
            return jsonify({"error": "Falta el nombre"}), 400
        cur = con.execute(
            "INSERT INTO items(nombre,categoria_id,unidad,cantidad,rotos,minimo,ubicacion,notas,alias,creado) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (nombre, d.get("categoria_id"), norm_unit(d.get("unidad") or "uds"), num(d.get("cantidad")),
             0, num(d.get("minimo")), d.get("ubicacion") or "", d.get("notas") or "", d.get("alias") or "", now()))
        it = dict(con.execute("SELECT * FROM items WHERE id=?", (cur.lastrowid,)).fetchone())
        log_mov(con, it, "alta", it["cantidad"], "Alta de material nuevo")
        con.commit()
        return jsonify(it)
    return jsonify(rows(con.execute(ITEM_SQL + " ORDER BY c.orden, c.id, i.nombre COLLATE NOCASE")))


@app.route("/api/items/<int:iid>", methods=["PUT", "DELETE"])
def item_api(iid):
    con = db()
    it = con.execute("SELECT * FROM items WHERE id=?", (iid,)).fetchone()
    if not it:
        abort(404)
    it = dict(it)
    if request.method == "DELETE":
        log_mov(con, it, "eliminado", it["cantidad"], "Material eliminado del inventario")
        con.execute("DELETE FROM items WHERE id=?", (iid,))
        con.commit()
        return jsonify({"ok": True})
    d = request.get_json(force=True) or {}
    nueva = num(d.get("cantidad"), it["cantidad"])
    nuevos_rotos = num(d.get("rotos"), it["rotos"])
    con.execute("UPDATE items SET nombre=?, categoria_id=?, unidad=?, cantidad=?, rotos=?, minimo=?, ubicacion=?, "
                "notas=?, alias=? WHERE id=?",
                ((d.get("nombre") or it["nombre"]).strip(), d.get("categoria_id"), norm_unit(d.get("unidad") or it["unidad"]),
                 nueva, nuevos_rotos, num(d.get("minimo"), it["minimo"]), d.get("ubicacion", it["ubicacion"]),
                 d.get("notas", it["notas"]), d.get("alias", it["alias"]), iid))
    if abs(nueva - it["cantidad"]) > 1e-9:
        log_mov(con, it, "ajuste", nueva - it["cantidad"], "Edición manual: %s → %s" % (fmt(it["cantidad"]), fmt(nueva)))
    con.commit()
    return jsonify(dict(con.execute(ITEM_SQL + " WHERE i.id=?", (iid,)).fetchone()))


@app.route("/api/items/<int:iid>/movimiento", methods=["POST"])
def movimiento(iid):
    con = db()
    it = con.execute("SELECT * FROM items WHERE id=?", (iid,)).fetchone()
    if not it:
        abort(404)
    it = dict(it)
    d = request.get_json(force=True) or {}
    tipo = d.get("tipo")
    n = abs(num(d.get("cantidad"), 0))
    nota = (d.get("nota") or "").strip()
    cant, rotos = float(it["cantidad"] or 0), float(it["rotos"] or 0)
    if n <= 0:
        return jsonify({"error": "Indica una cantidad mayor que 0"}), 400
    if tipo == "entrada":
        cant += n
    elif tipo == "baja":
        if n > cant + 1e-9:
            return jsonify({"error": "No puedes descontar más de lo disponible (%s %s)" % (fmt(cant), it["unidad"])}), 400
        cant -= n
    elif tipo == "rotura":
        if n > cant + 1e-9:
            return jsonify({"error": "Solo hay %s %s disponibles" % (fmt(cant), it["unidad"])}), 400
        cant -= n
        rotos += n
    elif tipo == "reparacion":
        if n > rotos + 1e-9:
            return jsonify({"error": "Solo hay %s marcados como rotos" % fmt(rotos)}), 400
        rotos -= n
        cant += n
    elif tipo == "desechar":
        if n > rotos + 1e-9:
            return jsonify({"error": "Solo hay %s marcados como rotos" % fmt(rotos)}), 400
        rotos -= n
    else:
        return jsonify({"error": "Tipo de movimiento no válido"}), 400
    con.execute("UPDATE items SET cantidad=?, rotos=? WHERE id=?", (cant, rotos, iid))
    log_mov(con, it, tipo, n, nota)
    con.commit()
    return jsonify(dict(con.execute(ITEM_SQL + " WHERE i.id=?", (iid,)).fetchone()))


@app.route("/api/movimientos")
def movimientos():
    lim = int(num(request.args.get("limite"), 300))
    return jsonify(rows(db().execute("SELECT * FROM movimientos ORDER BY id DESC LIMIT ?", (lim,))))


# ----------------------------------------------------------------- grupos
@app.route("/api/grupos", methods=["GET", "POST"])
def grupos_api():
    con = db()
    if request.method == "POST":
        d = request.get_json(force=True) or {}
        lista = parse_lista(d.get("lista"))
        con.execute("INSERT INTO grupos(curso,grupo,alumnos,agrupamiento,lista) VALUES (?,?,?,?,?)",
                    (d.get("curso") or "", d.get("grupo") or "", len(lista) or int(num(d.get("alumnos"), 20)),
                     max(0, int(num(d.get("agrupamiento"), 2))), "\n".join(lista)))
        con.commit()
    return jsonify(rows(con.execute("SELECT * FROM grupos ORDER BY curso, grupo")))


@app.route("/api/grupos/<int:gid>", methods=["PUT", "DELETE"])
def grupo_api(gid):
    con = db()
    if request.method == "DELETE":
        con.execute("DELETE FROM grupos WHERE id=?", (gid,))
    else:
        d = request.get_json(force=True) or {}
        lista = parse_lista(d.get("lista"))
        con.execute("UPDATE grupos SET curso=?, grupo=?, alumnos=?, agrupamiento=?, lista=? WHERE id=?",
                    (d.get("curso") or "", d.get("grupo") or "", len(lista) or int(num(d.get("alumnos"), 20)),
                     max(0, int(num(d.get("agrupamiento"), 2))), "\n".join(lista), gid))
    con.commit()
    return jsonify({"ok": True})


# ----------------------------------------------------------------- prácticas
def all_items():
    return rows(db().execute("SELECT id, nombre, alias, unidad FROM items"))


@app.route("/api/practicas/analizar", methods=["POST"])
def analizar():
    texto = ""
    pdf_file, pdf_nombre = "", ""
    f = request.files.get("pdf")
    if f and f.filename:
        if not f.filename.lower().endswith(".pdf"):
            return jsonify({"error": "El archivo debe ser un PDF"}), 400
        pdf_file = uuid.uuid4().hex + ".pdf"
        pdf_nombre = f.filename
        path = os.path.join(UPLOADS, pdf_file)
        f.save(path)
        texto = extract_pdf_text(path)
    extra = request.form.get("texto") or ""
    if extra.strip():
        texto = (texto + "\n" + extra) if texto else extra
    if not texto.strip():
        return jsonify({"error": "No se ha podido leer texto del PDF (¿es una imagen escaneada?). "
                                 "Pega la lista de materiales en el cuadro de texto.",
                        "pdf_file": pdf_file, "pdf_nombre": pdf_nombre}), 422
    mats = analyze_text(texto, all_items())
    if not mats and extra.strip():
        # texto pegado sin encabezado: cada línea es un material
        mats = []
        its = all_items()
        for line in extra.splitlines():
            for p in split_items(BULLET.sub("", line.strip())):
                if len(p) > 2:
                    it = parse_item(p)
                    m, s = match_item(it["nombre"], its)
                    it.update({"item_id": m["id"] if m else None, "confianza": round(s, 2), "ignorar": False})
                    mats.append(it)
    titulo = request.form.get("titulo") or guess_title(texto)
    return jsonify({"titulo": titulo, "texto": texto, "materiales": mats, "pdf_file": pdf_file,
                    "pdf_nombre": pdf_nombre})


@app.route("/api/emparejar", methods=["POST"])
def emparejar():
    d = request.get_json(force=True) or {}
    it, s = match_item(d.get("nombre") or "", all_items())
    return jsonify({"item_id": it["id"] if it else None, "confianza": round(s, 2)})


def save_aliases(con, materiales):
    """Recuerda los emparejamientos manuales como alias para futuras lecturas."""
    for m in materiales:
        if not m.get("item_id") or not m.get("manual"):
            continue
        it = con.execute("SELECT id, nombre, alias FROM items WHERE id=?", (m["item_id"],)).fetchone()
        if not it:
            continue
        nombre = (m.get("nombre") or "").strip()
        if not nombre or " ".join(tokens(nombre)) == " ".join(tokens(it["nombre"])):
            continue
        al = [a for a in (it["alias"] or "").split("|") if a]
        if nombre.lower() not in [a.lower() for a in al]:
            al.append(nombre)
            con.execute("UPDATE items SET alias=? WHERE id=?", ("|".join(al[-15:]), it["id"]))


@app.route("/api/practicas", methods=["GET", "POST"])
def practicas_api():
    con = db()
    if request.method == "POST":
        d = request.get_json(force=True) or {}
        mats = d.get("materiales") or []
        save_aliases(con, mats)
        cur = con.execute("INSERT INTO practicas(titulo,pdf_file,pdf_nombre,texto,materiales,creado,ajustes) "
                          "VALUES (?,?,?,?,?,?,?)",
                          (d.get("titulo") or "Práctica", d.get("pdf_file") or "", d.get("pdf_nombre") or "",
                           d.get("texto") or "", json.dumps(mats, ensure_ascii=False), now(),
                           json.dumps(d.get("ajustes") or {}, ensure_ascii=False)))
        con.commit()
        return jsonify({"id": cur.lastrowid})
    out = rows(con.execute("SELECT id, titulo, pdf_file, pdf_nombre, materiales, creado, ultima, ajustes "
                           "FROM practicas ORDER BY id DESC"))
    for p in out:
        p["ajustes"] = json.loads(p["ajustes"] or "{}")
        p["materiales"] = json.loads(p["materiales"] or "[]")
        p["ultima"] = json.loads(p["ultima"]) if p["ultima"] else None
    return jsonify(out)


@app.route("/api/practicas/<int:pid>", methods=["GET", "PUT", "DELETE"])
def practica_api(pid):
    con = db()
    p = con.execute("SELECT * FROM practicas WHERE id=?", (pid,)).fetchone()
    if not p:
        abort(404)
    if request.method == "DELETE":
        if p["pdf_file"]:
            try:
                os.remove(os.path.join(UPLOADS, p["pdf_file"]))
            except OSError:
                pass
        con.execute("DELETE FROM practicas WHERE id=?", (pid,))
        con.commit()
        return jsonify({"ok": True})
    if request.method == "PUT":
        d = request.get_json(force=True) or {}
        mats = d.get("materiales") or []
        save_aliases(con, mats)
        con.execute("UPDATE practicas SET titulo=?, materiales=?, ajustes=? WHERE id=?",
                    (d.get("titulo") or p["titulo"], json.dumps(mats, ensure_ascii=False),
                     json.dumps(d.get("ajustes") or {}, ensure_ascii=False), pid))
        con.commit()
        p = con.execute("SELECT * FROM practicas WHERE id=?", (pid,)).fetchone()
    p = dict(p)
    p["materiales"] = json.loads(p["materiales"] or "[]")
    p["ultima"] = json.loads(p["ultima"]) if p["ultima"] else None
    p["ajustes"] = json.loads(p.get("ajustes") or "{}")
    return jsonify(p)


@app.route("/api/practicas/<int:pid>/pdf")
def practica_pdf(pid):
    p = db().execute("SELECT pdf_file FROM practicas WHERE id=?", (pid,)).fetchone()
    if not p or not p["pdf_file"]:
        abort(404)
    return send_from_directory(UPLOADS, p["pdf_file"], mimetype="application/pdf")


def grupo_params(d):
    if d.get("grupo_id"):
        gr = db().execute("SELECT * FROM grupos WHERE id=?", (int(d["grupo_id"]),)).fetchone()
        if gr:
            gr = dict(gr)
            gr["nombres"] = parse_lista(gr.get("lista"))
            if gr["nombres"]:
                gr["alumnos"] = len(gr["nombres"])
            if d.get("agrupamiento") not in (None, ""):
                gr["agrupamiento"] = max(0, int(num(d.get("agrupamiento"), 2)))
            return gr
    return {"id": None, "curso": "", "grupo": "", "alumnos": int(num(d.get("alumnos"), 20)),
            "agrupamiento": max(0, int(num(d.get("agrupamiento"), 2))), "nombres": []}


def evaluar(materiales, alumnos, agrup, cfg):
    """Calcula la viabilidad. Con agrup = 0 (automático) elige la distribución:
    parejas -> tríos -> grupos de 4, la primera que quepa en el laboratorio y tenga material."""
    agrup = int(agrup or 0)
    res_t = {t: compute_viability(materiales, alumnos, t, cfg) for t in (1, 2, 3, 4)}

    def motivo_no(r):
        m = []
        if r["espacio"]:
            m.append("no caben en el laboratorio (%s)" % "; ".join(x.rstrip(".") for x in r["espacio"]))
        if r["faltas"]:
            m.append("falta material: %s" % ", ".join(l["nombre"] for l in r["faltas"][:4])
                     + ("…" if len(r["faltas"]) > 4 else ""))
        return " y ".join(m) or "no viable"

    alternativas = []
    for t in (1, 2, 3, 4):
        r = res_t[t]
        alternativas.append({"tam": t, "nombre": nombre_tamano(t, True), "viable": r["viable"], "grupos": r["grupos"],
                             "reparto_texto": r["reparto_texto"], "max_alumnos": r["max_alumnos"],
                             "motivo": "" if r["viable"] else motivo_no(r)})
    if agrup > 0:
        res = res_t.get(agrup) or compute_viability(materiales, alumnos, agrup, cfg)
        res["auto"] = False
        if not res["viable"]:
            mejor = [a for a in alternativas if a["viable"] and a["tam"] != agrup]
            if mejor:
                res["sugerencia"] = ("Trabajando por %s (%s) la práctica SÍ sería viable."
                                     % (mejor[0]["nombre"], mejor[0]["reparto_texto"]))
    else:
        orden = (2, 3, 4)
        elegido = next((t for t in orden if res_t[t]["viable"]), None)
        if elegido is None:
            elegido = max(orden, key=lambda t: (res_t[t]["max_alumnos"], -t))
        res = res_t[elegido]
        res["auto"] = True
        pasos = []
        for t in orden:
            if t == elegido:
                break
            pasos.append("por %s: %s" % (nombre_tamano(t, True), motivo_no(res_t[t])))
        if res["viable"]:
            base = "Distribución automática: se trabaja por %s (%s)." % (nombre_tamano(elegido, True), res["reparto_texto"])
        else:
            base = ("Distribución automática: ninguna agrupación es viable; la que más alumnos atiende es por %s."
                    % nombre_tamano(elegido, True))
        res["motivo_auto"] = base + ((" Descartado " + "; ".join(pasos) + ".") if pasos else "")
    res["alternativas"] = alternativas
    return res


@app.route("/api/viabilidad", methods=["POST"])
def viabilidad():
    d = request.get_json(force=True) or {}
    gr = grupo_params(d)
    res = evaluar(d.get("materiales") or [], gr["alumnos"], gr["agrupamiento"], get_config())
    res["grupo"] = gr
    res["equipos"] = equipos(gr.get("nombres") or [], res["reparto"])
    if d.get("practica_id"):
        resumen = {"viable": res["viable"], "fecha": now(), "grupo": "%s %s" % (gr["curso"], gr["grupo"]),
                   "alumnos": gr["alumnos"], "max_alumnos": res["max_alumnos"]}
        db().execute("UPDATE practicas SET ultima=? WHERE id=?",
                     (json.dumps(resumen, ensure_ascii=False), int(d["practica_id"])))
        db().commit()
    return jsonify(res)


@app.route("/api/practicas/<int:pid>/realizar", methods=["POST"])
def realizar(pid):
    """Descuenta del stock los materiales consumibles (reactivos) usados en la práctica."""
    con = db()
    p = con.execute("SELECT * FROM practicas WHERE id=?", (pid,)).fetchone()
    if not p:
        abort(404)
    d = request.get_json(force=True) or {}
    gr = grupo_params(d)
    alumnos = max(1, int(gr["alumnos"]))
    tam = int(gr["agrupamiento"] or 0)
    if tam <= 0:
        tam = evaluar(json.loads(p["materiales"] or "[]"), alumnos, 0, get_config())["agrupamiento"]
    grupos = len(distribuir(alumnos, tam))
    mats = json.loads(p["materiales"] or "[]")
    hechos = []
    for m in mats:
        if m.get("ignorar") or not m.get("item_id"):
            continue
        it = con.execute("SELECT i.*, c.consumible FROM items i LEFT JOIN categorias c ON c.id=i.categoria_id "
                         "WHERE i.id=?", (int(m["item_id"]),)).fetchone()
        if not it or not it["consumible"]:
            continue
        it = dict(it)
        f = unit_factor(m.get("unidad") or "uds", it["unidad"]) or 1.0
        q = num(m.get("cantidad"), 1) * f
        amb = m.get("ambito") or "grupo"
        usado = q if amb == "total" else (q * alumnos if amb == "alumno" else q * grupos)
        usado = min(usado, float(it["cantidad"] or 0))
        if usado <= 0:
            continue
        con.execute("UPDATE items SET cantidad=cantidad-? WHERE id=?", (usado, it["id"]))
        log_mov(con, it, "practica", usado, "Consumido en «%s» (%s %s, %d alumnos)"
                % (p["titulo"], gr["curso"], gr["grupo"], alumnos))
        hechos.append({"nombre": it["nombre"], "cantidad": round(usado, 3), "unidad": it["unidad"]})
    con.commit()
    return jsonify({"ok": True, "descontado": hechos})


# ----------------------------------------------------------------- informe PDF
def jpeg_size(data):
    """Ancho y alto de un JPEG leyendo su cabecera (sin librerías externas)."""
    i = 2
    while i < len(data) - 9:
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1]
        if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
            h = (data[i + 5] << 8) + data[i + 6]
            w = (data[i + 7] << 8) + data[i + 8]
            return w, h, data[i + 9]
        seg = (data[i + 2] << 8) + data[i + 3]
        i += 2 + seg
    return None


def _logo_jpeg(cfg):
    f = cfg.get("logo")
    if not f:
        return None
    path = os.path.join(DATA, f)
    if not os.path.exists(path):
        return None
    data = open(path, "rb").read()
    if data[:2] == b"\xff\xd8":
        sz = jpeg_size(data)
        if sz and sz[2] in (1, 3):
            return data, sz[0], sz[1], sz[2] == 1
    try:  # logos antiguos en PNG: se convierten si Pillow está disponible
        from PIL import Image
        im = Image.open(path)
        im.thumbnail((300, 300))
        if im.mode in ("RGBA", "LA", "P"):
            im = im.convert("RGBA")
            bg = Image.new("RGB", im.size, (255, 255, 255))
            bg.paste(im, mask=im.split()[-1])
            im = bg
        else:
            im = im.convert("RGB")
        b = io.BytesIO()
        im.save(b, "JPEG", quality=90)
        return b.getvalue(), im.size[0], im.size[1], False
    except Exception:
        return None


def q_txt(q, u):
    return "%s %s" % (fmt(q), u if u != "uds" else ("ud." if abs(q - 1) < 1e-9 else "uds."))


COLOR_TAM = {1: ("#e0f2fe", "#0369a1"), 2: ("#ccfbf1", "#0f766e"), 3: ("#fef3c7", "#b45309")}


def croquis(pdf, res, cfg, gr, eq, titulo, curso):
    """Hoja apaisada con el plano del laboratorio: mesas, puestos y nombres."""
    from pdfgen import text_width
    pdf.new_page(landscape=True)
    W, H, M = pdf.W, pdf.H, 30
    NAVY = "#0f2a44"
    reparto = res["reparto"]
    apm = int(res.get("alumnos_por_mesa") or 4)
    mesas = int(res.get("mesas") or 0)
    plano, sin = res.get("plano") or [], res.get("sin_puesto") or []
    aviso_mesas = ""
    if mesas <= 0:
        mesas = max(1, int(math.ceil(sum(reparto) / float(apm))))
        plano, sin = asignar_mesas(reparto, mesas, apm)
        aviso_mesas = "No hay mesas configuradas: se muestra una distribución orientativa."
    mpf = max(1, int(num(cfg.get("mesas_por_fila"), 4)))
    nombres_reales = bool(gr.get("nombres"))

    # cabecera
    pdf.rect(0, H, W, 46, fill=NAVY)
    pdf.text(M, H - 22, "CROQUIS DEL LABORATORIO · Puestos de trabajo", 14, True, "#ffffff")
    pdf.text(M, H - 37, "%s  ·  %s  ·  %d alumnos: %s" % (titulo[:70], curso, res["alumnos"], res["reparto_texto"]),
             9, False, "#99f6e4")
    pdf.text(M, H - 22, cfg.get("instituto", ""), 9.5, False, "#cbd5e1", "right", W - 2 * M)

    # zona frontal: pizarra, profesor, puerta
    top = H - 62
    pw = 260
    pdf.rect((W - pw) / 2, top, pw, 12, fill="#334155")
    pdf.text((W - pw) / 2, top - 9, "PIZARRA", 7.5, True, "#ffffff", "center", pw)
    pdf.rect(M, top - 4, 130, 30, fill="#f1f5f9", stroke="#64748b", lw=0.8)
    pdf.text(M, top - 22, "Mesa del profesor", 8.5, True, "#334155", "center", 130)
    pdf.rect(W - M - 8, top - 2, 8, 44, fill="#a16207")
    pdf.text(W - M - 60, top - 24, "PUERTA", 7.5, True, "#a16207")

    # rejilla de mesas
    filas = int(math.ceil(mesas / float(mpf)))
    cols = min(mpf, mesas)
    area_top = top - 46
    area_bottom = 62 if not sin else 84
    gap_x, gap_y = 16, 16
    mw = (W - 2 * M - gap_x * (cols - 1)) / cols
    mh = min(150, (area_top - area_bottom - gap_y * (filas - 1)) / filas)
    total_h = filas * mh + gap_y * (filas - 1)
    y0 = area_top - max(0, (area_top - area_bottom - total_h) / 2)

    def fit(s, size, width, bold=False):
        if text_width(s, size, bold) <= width:
            return s
        while s and text_width(s + ".", size, bold) > width:
            s = s[:-1]
        return s + "."

    for m in range(mesas):
        r, c = divmod(m, mpf)
        x = M + c * (mw + gap_x)
        y = y0 - r * (mh + gap_y)
        pdf.rect(x, y, mw, mh, fill="#e2e8f0", stroke="#475569", lw=1.1)
        pdf.text(x + 5, y - 10, "MESA %d" % (m + 1), 7.5, True, "#334155")
        grupos = plano[m] if m < len(plano) else []
        inner_x, inner_w = x + 4, mw - 8
        inner_top, inner_h = y - 14, mh - 18
        cx = inner_x
        ocupados = sum(reparto[g] for g in grupos)
        unidades = max(apm, ocupados)
        for gi in grupos:
            s = reparto[gi]
            cw = inner_w * s / float(unidades) - 2
            fill, ink = COLOR_TAM.get(s, ("#ede9fe", "#6d28d9"))
            pdf.rect(cx, inner_top, cw, inner_h, fill=fill, stroke=ink, lw=0.8)
            etiqueta = "%s %d · %s" % ("P" if s == 1 else "G", gi + 1, nombre_tamano(s).capitalize())
            pdf.text(cx + 3, inner_top - 9, fit(etiqueta, 7, cw - 6, True), 7, True, ink)
            nombres = eq[gi] if gi < len(eq) else []
            size = 7.2
            while size > 5 and (len(nombres) * size * 1.2 > inner_h - 14):
                size -= 0.4
            yy = inner_top - 9 - size * 1.35
            for nm in nombres:
                pdf.text(cx + 3, yy, fit(nm, size, cw - 6), size, False, "#0f172a")
                yy -= size * 1.25
            cx += cw + 2
        libres = unidades - ocupados
        if libres > 0:
            cw = inner_x + inner_w - cx
            if cw > 6:
                pdf.rect(cx, inner_top, cw, inner_h, fill="#f8fafc", stroke="#cbd5e1", lw=0.5)
                pdf.text(cx, inner_top - inner_h / 2 - 3, fit("libre (%d)" % libres, 6.5, cw - 2), 6.5, False,
                         "#94a3b8", "center", cw)

    # puestos sin mesa
    yb = area_bottom - 14
    if sin:
        txt = "Sin mesa disponible: " + "; ".join("G%d (%s)" % (g + 1, ", ".join(eq[g]) if g < len(eq) else "") for g in sin)
        for ln in pdf.wrap(txt, 8, W - 2 * M, True)[:2]:
            pdf.text(M, yb + 18, ln, 8, True, "#b91c1c")
            yb -= 10
    # leyenda
    lx = M
    for s, lab in ((1, "Individual"), (2, "Pareja"), (3, "Grupo de 3"), (4, "Grupo de 4")):
        if s not in reparto and not (s == 4 and any(x >= 4 for x in reparto)):
            continue
        fill, ink = COLOR_TAM.get(s, ("#ede9fe", "#6d28d9"))
        pdf.rect(lx, 44, 12, 9, fill=fill, stroke=ink)
        pdf.text(lx + 16, 36.5, lab, 8, False, "#334155")
        lx += 30 + text_width(lab, 8)
    nota = aviso_mesas or ("Nombres según la lista del grupo." if nombres_reales else
                           "Sin listado de alumnos: añade los nombres en «Cursos y grupos» para verlos en el plano.")
    pdf.text(lx + 10, 36.5, nota, 7.5, False, "#64748b")


def build_report(titulo, res, cfg):
    from pdfgen import PDF, text_width
    gr = res.get("grupo") or {}
    curso = ("%s %s" % (gr.get("curso", ""), gr.get("grupo", ""))).strip() or "Grupo personalizado"
    pdf = PDF(title="Informe - " + titulo)
    pdf.footer = "%s · %s · Informe generado el %s" % (cfg.get("instituto", ""), cfg.get("laboratorio", ""), now())
    M, W = pdf.M, pdf.W - 2 * pdf.M
    NAVY, TEAL = "#0f2a44", "#0d9488"

    # cabecera
    h = 78
    pdf.rect(0, pdf.H, pdf.W, h + 20, fill=NAVY)
    pdf.rect(0, pdf.H - h - 20, pdf.W, 4, fill=TEAL)
    x_text = M
    logo = _logo_jpeg(cfg)
    if logo:
        data, pw, ph, gris = logo
        s = 58.0 / max(pw, ph)
        pdf.rect(M - 3, pdf.H - 17, pw * s + 6, ph * s + 6, fill="#ffffff")
        pdf.image_jpeg(data, pw, ph, M, pdf.H - 20, pw * s, ph * s, gray=gris)
        x_text = M + pw * s + 16
    pdf.text(x_text, pdf.H - 38, cfg.get("instituto", ""), 16, True, "#ffffff")
    pdf.text(x_text, pdf.H - 54, cfg.get("departamento", ""), 9.5, False, "#99f6e4")
    pdf.text(x_text, pdf.H - 72, "INFORME DE DISTRIBUCIÓN DE MATERIAL", 10.5, True, "#ffffff")
    pdf.text(M, pdf.H - 38, "Fecha: " + datetime.now().strftime("%d/%m/%Y"), 9, False, "#cbd5e1", "right", W)
    pdf.y = pdf.H - h - 40

    pdf.paragraph(titulo, 15, True, NAVY)
    pdf.y -= 2
    pdf.paragraph("Curso / grupo: %s   ·   %d alumnos   ·   Trabajo por %s"
                  % (curso, res["alumnos"], res["nombre_agrupamiento"]), 10, False, "#334155")
    pdf.y -= 10

    # veredicto
    ok = res["viable"]
    col, bg = ("#15803d", "#dcfce7") if ok else ("#b91c1c", "#fee2e2")
    bh = 62
    pdf.ensure(bh)
    pdf.rect(M, pdf.y, W, bh, fill=bg, stroke=col, lw=1.4)
    big = "ES VIABLE" if ok else "NO ES VIABLE"
    pdf.text(M, pdf.y - 34, big, 26, True, col, "center", W)
    sub = ("Hay material y espacio suficientes para todo el grupo." if ok else
           "Con el stock actual alcanza para %d de %d alumnos (%s)."
           % (res["max_alumnos"], res["alumnos"], res["reparto_max_texto"] if res["max_alumnos"] else "ningún grupo"))
    pdf.text(M, pdf.y - 52, sub, 10, False, col, "center", W)
    pdf.y -= bh + 16

    def section(t):
        pdf.ensure(40)
        pdf.y -= 6
        pdf.rect(M, pdf.y, 4, 15, fill=TEAL)
        pdf.text(M + 10, pdf.y - 11.5, t, 12, True, NAVY)
        pdf.y -= 24

    if not ok:
        section("Qué falta")
        if res["faltas"]:
            rws = []
            for l in res["faltas"]:
                estado = "No existe en el stock" if l.get("sin_stock") else (
                    "Faltan %s%s" % (q_txt(l["falta"], l["unidad"]),
                                     (" (%s rotos)" % fmt(l["rotos"])) if l.get("rotos") else ""))
                rws.append([l["nombre"], q_txt(l["necesario"], l["unidad"]), q_txt(l["disponible"], l["unidad"]), estado])
            pdf.table(["Material", "Necesario", "Disponible", "Falta"], rws, [W * .40, W * .17, W * .17, W * .26],
                      header_bg="#b91c1c", row_colors=["#fff1f2"] * len(rws), aligns=["left", "right", "right", "left"])
        for e in res["espacio"]:
            pdf.paragraph("• " + e, 9.5, False, "#b91c1c")
        pdf.y -= 4

    # reparto
    section("Reparto de alumnos")
    pdf.paragraph("%d alumnos → %d puestos de trabajo: %s." % (res["alumnos"], res["grupos"], res["reparto_texto"]),
                  10, True, "#0f172a")
    if res.get("motivo_auto"):
        pdf.paragraph(res["motivo_auto"], 9, False, "#0f766e")
    if res.get("sugerencia"):
        pdf.paragraph("Sugerencia: " + res["sugerencia"], 9, True, "#b45309")
    if res["agrupamiento"] > 1 and res["alumnos"] % res["agrupamiento"]:
        pdf.paragraph("El número de alumnos no es múltiplo de %d, así que el reparto combina grupos de distinto tamaño "
                      "para que nadie se quede solo." % res["agrupamiento"], 9, False, "#475569")
    pdf.y -= 4
    mesa_de = {}
    for m, gs in enumerate(res.get("plano") or [], 1):
        for gi in gs:
            mesa_de[gi] = m
    nombres = gr.get("nombres") or []
    eq = res.get("equipos") or equipos(nombres, res["reparto"])
    rws = []
    for i, s in enumerate(res["reparto"]):
        mesa = str(mesa_de[i]) if i in mesa_de else ("sin mesa" if res.get("mesas") else "-")
        quien = ", ".join(eq[i]) if nombres else "_" * 38
        rws.append(["%s %d" % ("Puesto" if s == 1 else "Grupo", i + 1), nombre_tamano(s).capitalize(), str(s), mesa, quien])
    pdf.table(["Puesto", "Tipo", "Alumnos", "Mesa", "Nombres de los alumnos"], rws,
              [W * .13, W * .15, W * .10, W * .10, W * .52], aligns=["left", "left", "center", "center", "left"], size=8.5)

    alts = res.get("alternativas") or []
    if alts:
        pdf.y -= 6
        pdf.paragraph("Comparativa de agrupamientos posibles:", 9.5, True, "#334155")
        pdf.y -= 2
        pdf.table(["Agrupamiento", "Reparto", "¿Viable?", "Alumnos atendidos / motivo"],
                  [[a["nombre"].capitalize() + ("  (elegido)" if a["tam"] == res["agrupamiento"] else ""), a["reparto_texto"],
                    "SÍ" if a["viable"] else "NO",
                    "%d de %d" % (a["max_alumnos"], res["alumnos"]) + ("" if a["viable"] else " · " + a["motivo"])]
                   for a in alts], [W * .2, W * .27, W * .1, W * .43], header_bg="#334155", size=8,
                  row_colors=["#ecfdf5" if a["tam"] == res["agrupamiento"] else None for a in alts])

    # material por puesto
    section("Material que recibe cada puesto de trabajo")
    lineas_ok = [l for l in res["lineas"]]
    tamanos = sorted(set(res["reparto"]))
    cuenta = {s: res["reparto"].count(s) for s in tamanos}
    for s in tamanos:
        kit = kit_para(lineas_ok, s)
        pdf.ensure(36)
        pdf.paragraph("Cada %s (%d puesto%s):" % (nombre_tamano(s), cuenta[s], "s" if cuenta[s] > 1 else ""),
                      10.5, True, TEAL)
        pdf.y -= 2
        if kit:
            pdf.table(["Material", "Cantidad"], [[n, q_txt(q, u)] for n, q, u in kit], [W * .75, W * .25],
                      header_bg="#134e4a", aligns=["left", "right"])
        else:
            pdf.paragraph("Sin material asignado por puesto.", 9, False, "#64748b")
        pdf.y -= 8
    fijos = [l for l in res["lineas"] if l["fijo"] > 0]
    if fijos:
        pdf.paragraph("Material común (mesa del profesor):", 10.5, True, TEAL)
        pdf.y -= 2
        pdf.table(["Material", "Cantidad"], [[l["nombre"], q_txt(l["fijo"], l["unidad"])] for l in fijos],
                  [W * .75, W * .25], header_bg="#134e4a", aligns=["left", "right"])

    # resumen total
    section("Recuento total frente al stock")
    rws, colors = [], []
    for l in res["lineas"]:
        estado = "OK" if l["ok"] else ("No está en stock" if l.get("sin_stock") else "Faltan " + q_txt(l["falta"], l["unidad"]))
        rws.append([l["nombre"], l["categoria"].capitalize(), q_txt(l["necesario"], l["unidad"]) + (" *" if l["margen"] else ""),
                    q_txt(l["disponible"], l["unidad"]), estado])
        colors.append(None if l["ok"] else "#fff1f2")
    if rws:
        pdf.table(["Material", "Categoría", "Necesario", "En stock", "Estado"], rws,
                  [W * .34, W * .16, W * .16, W * .14, W * .20], row_colors=colors,
                  aligns=["left", "left", "right", "right", "left"])
    if any(l["margen"] for l in res["lineas"]):
        pdf.paragraph("* Incluye un margen de seguridad del %s %% en reactivos y cantidades no unitarias." % fmt(res["margen"]),
                      8, False, "#64748b")
    for a in res["avisos"]:
        pdf.paragraph("Aviso: " + a, 8.5, False, "#b45309")

    # firma
    pdf.ensure(70)
    pdf.y -= 40
    pdf.line(M, pdf.y, M + 200, pdf.y, "#94a3b8")
    pdf.line(M + W - 200, pdf.y, M + W, pdf.y, "#94a3b8")
    pdf.text(M, pdf.y - 12, "Profesor/a responsable", 8.5, False, "#475569")
    pdf.text(M + W - 200, pdf.y - 12, "Material preparado / revisado", 8.5, False, "#475569")
    croquis(pdf, res, cfg, gr, eq, titulo, curso)
    return pdf.output()


@app.route("/api/informe", methods=["POST"])
def informe():
    d = request.get_json(force=True) or {}
    gr = grupo_params(d)
    cfg = get_config()
    res = evaluar(d.get("materiales") or [], gr["alumnos"], gr["agrupamiento"], cfg)
    res["grupo"] = gr
    res["equipos"] = equipos(gr.get("nombres") or [], res["reparto"], bool(d.get("aleatorio")))
    titulo = d.get("titulo") or "Práctica de laboratorio"
    data = build_report(titulo, res, cfg)
    nombre = re.sub(r"[^A-Za-z0-9_-]+", "_", strip_accents(titulo))[:50].strip("_") or "practica"
    curso = re.sub(r"[^A-Za-z0-9_-]+", "_", strip_accents("%s_%s" % (gr.get("curso", ""), gr.get("grupo", "")))).strip("_")
    fname = "Informe_%s%s.pdf" % (nombre, ("_" + curso) if curso else "")
    resp = app.response_class(data, mimetype="application/pdf")
    resp.headers["Content-Disposition"] = "attachment; filename=\"%s\"" % fname
    return resp


# ----------------------------------------------------------------- proyectos (exportar / importar)
@app.route("/api/practicas/<int:pid>/exportar")
def exportar(pid):
    import zipfile
    con = db()
    p = con.execute("SELECT * FROM practicas WHERE id=?", (pid,)).fetchone()
    if not p:
        abort(404)
    p = dict(p)
    ajustes = json.loads(p.get("ajustes") or "{}")
    grupo = None
    if ajustes.get("grupo_id"):
        g_ = con.execute("SELECT curso, grupo, alumnos, agrupamiento, lista FROM grupos WHERE id=?",
                         (int(ajustes["grupo_id"]),)).fetchone()
        grupo = dict(g_) if g_ else None
    items = {r["id"]: dict(r) for r in con.execute(
        "SELECT i.id, i.nombre, i.unidad, c.nombre AS categoria FROM items i LEFT JOIN categorias c ON c.id=i.categoria_id")}
    mats = json.loads(p["materiales"] or "[]")
    for m in mats:
        it = items.get(m.get("item_id"))
        m["stock_nombre"] = it["nombre"] if it else None
        m["stock_categoria"] = it["categoria"] if it else None
        m["stock_unidad"] = it["unidad"] if it else None
    proyecto = {
        "formato": "laboratorio-fyq-proyecto", "version": 1, "exportado": now(),
        "instituto": get_config().get("instituto", ""),
        "titulo": p["titulo"], "texto": p["texto"], "materiales": mats,
        "ajustes": ajustes, "grupo": grupo, "pdf_nombre": p["pdf_nombre"], "ultima": json.loads(p["ultima"] or "null"),
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("proyecto.json", json.dumps(proyecto, ensure_ascii=False, indent=2))
        if p["pdf_file"] and os.path.exists(os.path.join(UPLOADS, p["pdf_file"])):
            z.write(os.path.join(UPLOADS, p["pdf_file"]), "guion.pdf")
    nombre = re.sub(r"[^A-Za-z0-9_-]+", "_", strip_accents(p["titulo"] or "practica"))[:50].strip("_") or "practica"
    resp = app.response_class(buf.getvalue(), mimetype="application/zip")
    resp.headers["Content-Disposition"] = "attachment; filename=\"Proyecto_%s.labfyq\"" % nombre
    return resp


@app.route("/api/practicas/importar", methods=["POST"])
def importar():
    import zipfile
    f = request.files.get("proyecto")
    if not f:
        return jsonify({"error": "No se ha recibido ningún archivo"}), 400
    try:
        z = zipfile.ZipFile(io.BytesIO(f.read()))
        proyecto = json.loads(z.read("proyecto.json").decode("utf-8"))
    except Exception:
        return jsonify({"error": "El archivo no es un proyecto válido de Laboratorio FyQ (.labfyq)"}), 400
    if proyecto.get("formato") != "laboratorio-fyq-proyecto":
        return jsonify({"error": "El archivo no es un proyecto de Laboratorio FyQ"}), 400
    con = db()
    items = all_items()
    by_name = {" ".join(tokens(i["nombre"])): i for i in items}
    no_encontrados = []
    mats = proyecto.get("materiales") or []
    for m in mats:
        it = None
        if m.get("stock_nombre"):
            it = by_name.get(" ".join(tokens(m["stock_nombre"])))
            if not it:
                it, _s = match_item(m["stock_nombre"], items)
        if not it and not m.get("ignorar"):
            it, _s = match_item(m.get("nombre") or "", items)
        m["item_id"] = it["id"] if it else None
        if not it and not m.get("ignorar"):
            no_encontrados.append(m.get("stock_nombre") or m.get("nombre"))
        for k in ("stock_nombre", "stock_categoria", "stock_unidad"):
            m.pop(k, None)
    ajustes = proyecto.get("ajustes") or {}
    gr = proyecto.get("grupo")
    grupo_creado = False
    if gr:
        ex = con.execute("SELECT id FROM grupos WHERE curso=? AND grupo=?", (gr.get("curso"), gr.get("grupo"))).fetchone()
        if ex:
            ajustes["grupo_id"] = ex["id"]
            if gr.get("lista"):
                cur_l = con.execute("SELECT lista FROM grupos WHERE id=?", (ex["id"],)).fetchone()["lista"]
                if not cur_l:
                    con.execute("UPDATE grupos SET lista=?, alumnos=? WHERE id=?",
                                (gr["lista"], len(parse_lista(gr["lista"])), ex["id"]))
        else:
            cur = con.execute("INSERT INTO grupos(curso,grupo,alumnos,agrupamiento,lista) VALUES (?,?,?,?,?)",
                              (gr.get("curso") or "", gr.get("grupo") or "", int(gr.get("alumnos") or 20),
                               int(gr.get("agrupamiento") or 2), gr.get("lista") or ""))
            ajustes["grupo_id"] = cur.lastrowid
            grupo_creado = True
    pdf_file = ""
    if "guion.pdf" in z.namelist():
        pdf_file = uuid.uuid4().hex + ".pdf"
        with open(os.path.join(UPLOADS, pdf_file), "wb") as out:
            out.write(z.read("guion.pdf"))
    cur = con.execute("INSERT INTO practicas(titulo,pdf_file,pdf_nombre,texto,materiales,creado,ajustes) VALUES (?,?,?,?,?,?,?)",
                      (proyecto.get("titulo") or "Práctica importada", pdf_file, proyecto.get("pdf_nombre") or "",
                       proyecto.get("texto") or "", json.dumps(mats, ensure_ascii=False), now(),
                       json.dumps(ajustes, ensure_ascii=False)))
    con.commit()
    return jsonify({"id": cur.lastrowid, "no_encontrados": no_encontrados, "grupo_creado": grupo_creado})


# ----------------------------------------------------------------- copia del stock (exportar / importar)
@app.route("/api/stock/exportar")
def stock_exportar():
    con = db()
    ahora = datetime.now()
    cats = rows(con.execute("SELECT id, nombre, color, consumible, orden FROM categorias ORDER BY orden, id"))
    cat_nom = {c["id"]: c["nombre"] for c in cats}
    items = rows(con.execute("SELECT * FROM items ORDER BY nombre COLLATE NOCASE"))
    data = {
        "formato": "laboratorio-fyq-stock", "version": 1,
        "fecha_exportacion": ahora.strftime("%Y-%m-%d %H:%M:%S"),
        "instituto": get_config().get("instituto", ""),
        "categorias": [{k: c[k] for k in ("nombre", "color", "consumible", "orden")} for c in cats],
        "items": [{
            "nombre": i["nombre"], "categoria": cat_nom.get(i["categoria_id"]), "unidad": i["unidad"],
            "cantidad": i["cantidad"], "rotos": i["rotos"], "minimo": i["minimo"], "ubicacion": i["ubicacion"],
            "notas": i["notas"], "alias": i["alias"], "creado": i["creado"],
        } for i in items],
    }
    inst = re.sub(r"[^A-Za-z0-9_-]+", "_", strip_accents(data["instituto"]))[:30].strip("_")
    fname = "Stock_%s%s.json" % ((inst + "_") if inst else "", ahora.strftime("%Y-%m-%d_%H-%M-%S"))
    resp = app.response_class(json.dumps(data, ensure_ascii=False, indent=1), mimetype="application/json")
    resp.headers["Content-Disposition"] = "attachment; filename=\"%s\"" % fname
    return resp


@app.route("/api/stock/importar", methods=["POST"])
def stock_importar():
    f = request.files.get("stock")
    if not f:
        return jsonify({"error": "No se ha recibido ningún archivo"}), 400
    try:
        data = json.loads(f.read().decode("utf-8-sig"))
        assert data.get("formato") == "laboratorio-fyq-stock"
    except Exception:
        return jsonify({"error": "El archivo no es una copia de stock de Laboratorio FyQ"}), 400
    modo = request.form.get("modo") or "fusionar"
    simular = request.form.get("simular") == "1"
    con = db()
    actuales = {r["nombre"].strip().lower(): dict(r) for r in con.execute("SELECT * FROM items")}
    nombres_archivo = set()
    nuevos, actualizados, iguales, cambios = 0, 0, 0, []
    for it in data.get("items") or []:
        k = (it.get("nombre") or "").strip().lower()
        if not k:
            continue
        nombres_archivo.add(k)
        a = actuales.get(k)
        if not a:
            nuevos += 1
        elif abs(num(a["cantidad"]) - num(it.get("cantidad"))) > 1e-9 or abs(num(a["rotos"]) - num(it.get("rotos"))) > 1e-9:
            actualizados += 1
            cambios.append({"nombre": it["nombre"], "antes": a["cantidad"], "despues": num(it.get("cantidad")), "unidad": it.get("unidad")})
        else:
            iguales += 1
    eliminar = [a["nombre"] for k, a in actuales.items() if k not in nombres_archivo] if modo == "reemplazar" else []
    resumen = {"fecha_exportacion": data.get("fecha_exportacion"), "instituto": data.get("instituto"),
               "total": len(data.get("items") or []), "nuevos": nuevos, "actualizados": actualizados,
               "iguales": iguales, "eliminados": len(eliminar), "lista_eliminados": eliminar[:30],
               "cambios": cambios[:40], "modo": modo}
    if simular:
        return jsonify(resumen)

    # categorías
    cats = {r["nombre"]: r["id"] for r in con.execute("SELECT id, nombre FROM categorias")}
    for c in data.get("categorias") or []:
        n = (c.get("nombre") or "").strip().upper()
        if n and n not in cats:
            cur = con.execute("INSERT INTO categorias(nombre,color,consumible,orden) VALUES (?,?,?,?)",
                              (n, c.get("color") or "#14b8a6", 1 if c.get("consumible") else 0, int(c.get("orden") or 9)))
            cats[n] = cur.lastrowid
        elif n:
            con.execute("UPDATE categorias SET color=?, consumible=? WHERE id=?",
                        (c.get("color") or "#14b8a6", 1 if c.get("consumible") else 0, cats[n]))
    nota = "Importado de copia del %s" % (data.get("fecha_exportacion") or "?")
    for it in data.get("items") or []:
        k = (it.get("nombre") or "").strip().lower()
        if not k:
            continue
        cid = cats.get((it.get("categoria") or "").strip().upper())
        vals = (cid, norm_unit(it.get("unidad") or "uds"), num(it.get("cantidad")), num(it.get("rotos")), num(it.get("minimo")),
                it.get("ubicacion") or "", it.get("notas") or "", it.get("alias") or "")
        a = actuales.get(k)
        if a:
            con.execute("UPDATE items SET categoria_id=?, unidad=?, cantidad=?, rotos=?, minimo=?, ubicacion=?, notas=?, alias=? "
                        "WHERE id=?", vals + (a["id"],))
            if abs(num(a["cantidad"]) - num(it.get("cantidad"))) > 1e-9:
                log_mov(con, a, "importacion", num(it.get("cantidad")) - num(a["cantidad"]),
                        "%s (%s → %s)" % (nota, fmt(a["cantidad"]), fmt(num(it.get("cantidad")))))
        else:
            cur = con.execute("INSERT INTO items(nombre,categoria_id,unidad,cantidad,rotos,minimo,ubicacion,notas,alias,creado) "
                              "VALUES (?,?,?,?,?,?,?,?,?,?)", (it["nombre"].strip(),) + vals + (it.get("creado") or now(),))
            log_mov(con, {"id": cur.lastrowid, "nombre": it["nombre"], "unidad": vals[1]}, "importacion", vals[2], nota)
    for k, a in actuales.items():
        if modo == "reemplazar" and k not in nombres_archivo:
            log_mov(con, a, "eliminado", a["cantidad"], nota + " (no estaba en la copia)")
            con.execute("DELETE FROM items WHERE id=?", (a["id"],))
    con.execute("INSERT OR REPLACE INTO config(clave, valor) VALUES ('ultima_importacion_stock', ?)",
                ("%s|%s" % (now(), data.get("fecha_exportacion") or ""),))
    con.commit()
    return jsonify(resumen)


# ----------------------------------------------------------------- inventario de ejemplo
DEMO = {
    "RECIPIENTES": [
        ("Vaso de precipitados 100 mL", 20), ("Vaso de precipitados 250 mL", 16), ("Vaso de precipitados 600 mL", 6),
        ("Matraz Erlenmeyer 250 mL", 12), ("Matraz aforado 100 mL", 6), ("Probeta 10 mL", 10),
        ("Probeta 100 mL", 12), ("Tubo de ensayo", 80), ("Vidrio de reloj", 15), ("Cristalizador", 6),
        ("Frasco lavador", 10), ("Embudo de vidrio", 10), ("Placa Petri", 20),
    ],
    "REACTIVOS": [
        ("Agua destilada", 10, "L"), ("Sulfato de cobre (II) pentahidratado", 500, "g"), ("Cloruro de sodio", 1000, "g"),
        ("Ácido clorhídrico 1 M", 1000, "mL"), ("Hidróxido de sodio 1 M", 1000, "mL"), ("Fenolftaleína", 100, "mL"),
        ("Bicarbonato de sodio", 500, "g"), ("Vinagre", 2, "L"), ("Etanol 96%", 1000, "mL"), ("Limaduras de hierro", 250, "g"),
    ],
    "INSTRUMENTOS": [
        ("Balanza electrónica", 4), ("Termómetro", 12), ("Mechero Bunsen", 8), ("Soporte universal", 12),
        ("Pinza de bureta", 10), ("Nuez doble", 14), ("Rejilla", 8), ("Trípode", 8), ("Bureta 50 mL", 6),
        ("Pipeta graduada 10 mL", 12), ("Dinamómetro", 10), ("Polímetro", 6), ("Cronómetro", 12), ("Regla 1 m", 8),
        ("Gradilla", 12), ("Pinzas de madera", 14), ("Espátula", 14), ("Varilla de vidrio", 16), ("Imán", 10),
    ],
    "OTROS": [
        ("Papel de filtro", 200), ("Papel indicador universal", 100), ("Gafas de seguridad", 30), ("Guantes de nitrilo", 200),
        ("Cuentagotas", 20), ("Cerillas", 5),
    ],
}


@app.route("/api/demo", methods=["POST"])
def demo():
    con = db()
    cats = {r["nombre"]: r["id"] for r in con.execute("SELECT id, nombre FROM categorias")}
    for cat, lista in DEMO.items():
        cid = cats.get(cat)
        if cid is None:
            cur = con.execute("INSERT INTO categorias(nombre,color,consumible,orden) VALUES (?,?,?,?)", (cat, "#14b8a6", 0, 9))
            cid = cur.lastrowid
        for e in lista:
            nombre, cant = e[0], e[1]
            unidad = e[2] if len(e) > 2 else "uds"
            if con.execute("SELECT 1 FROM items WHERE nombre=?", (nombre,)).fetchone():
                continue
            cur = con.execute("INSERT INTO items(nombre,categoria_id,unidad,cantidad,minimo,creado) VALUES (?,?,?,?,?,?)",
                              (nombre, cid, unidad, cant, 0, now()))
            log_mov(con, {"id": cur.lastrowid, "nombre": nombre, "unidad": unidad}, "alta", cant, "Inventario de ejemplo")
    con.commit()
    return jsonify({"ok": True})


@app.route("/api/resumen")
def resumen():
    con = db()
    r = {
        "items": con.execute("SELECT COUNT(*) FROM items").fetchone()[0],
        "rotos": con.execute("SELECT COUNT(*) FROM items WHERE rotos>0").fetchone()[0],
        "bajo_minimo": con.execute("SELECT COUNT(*) FROM items WHERE minimo>0 AND cantidad<minimo").fetchone()[0],
        "agotados": con.execute("SELECT COUNT(*) FROM items WHERE cantidad<=0").fetchone()[0],
        "practicas": con.execute("SELECT COUNT(*) FROM practicas").fetchone()[0],
        "grupos": con.execute("SELECT COUNT(*) FROM grupos").fetchone()[0],
    }
    return jsonify(r)


if __name__ == "__main__":
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w")
    init_db()
    try:  # sin mensaje de arranque en consola (la versión instalada no tiene consola)
        import flask.cli
        flask.cli.show_server_banner = lambda *a, **k: None
    except Exception:
        pass
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8642
    app.run(host="127.0.0.1", port=port, debug=False, threaded=True)
