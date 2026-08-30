#!/usr/bin/env python3
"""
harvest.py — read every wire in sources.json, keep what is about the search for
life beyond Earth, tag it by subject, and write wire.json.

Standard library only. No API keys, no paid services, no model calls.
Nothing here rewrites a headline: titles and snippets are the publishers' own,
truncated but never reworded, and every row keeps its original link.

    python3 harvest.py                 # normal run
    python3 harvest.py --dry-run       # harvest, print a report, write nothing
    python3 harvest.py --fixtures DIR  # read *.xml from DIR instead of the network
"""

import argparse
import gzip
import html
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

HERE = os.path.dirname(os.path.abspath(__file__))
SOURCES_PATH = os.path.join(HERE, "sources.json")
OUT_PATH = os.path.join(HERE, "wire.json")

RETAIN_DAYS = 45          # older stories are dropped on every run
MAX_ITEMS = 900           # hard cap on wire.json, newest kept
SNIPPET_CHARS = 240
TIMEOUT = 25
WORKERS = 10         # a few hundred wires now
USER_AGENT = ("Mozilla/5.0 (compatible; space-life-news/1.0; "
              "+https://github.com/WelcomeToYourGalaxy/space-life-news)")

# --------------------------------------------------------------------------
# Subjects.  `t` is the term; `g` is a guard list — the term only counts when
# one of the guards is also present.  Guards exist because "mars" is March in
# French, "Europa" is a continent and a football tournament in six of these
# languages, and Titan is a security company.
# --------------------------------------------------------------------------
TOPICS = [
    ("mars", "Mars", [
        ("perseverance", ["rover", "nasa", "mars", "jezero"]), ("jezero", None), ("cheyava", None),
        ("mars sample return", None), ("curiosity rover", None), ("tianwen", None), ("exomars", None),
        ("marte", ["vida", "nasa", "muestra", "rover", "planeta", "sonda", "marziano", "campioni", "amostra"]),
        ("mars", ["rover", "nasa", "planet", "planète", "martian*", "martien*", "marsprobe", "marsproben",
                  "sample", "leben", "vie", "life", "esa", "jpl", "orbiter", "jezero", "perseverance"]),
        ("martian*", None), ("martien*", None), ("火星", None), ("화성", None), ("марс", None),
        ("المريخ", None), ("मंगल", None), ("mangal grah", None),
    ]),
    ("europa", "Europa", [
        ("europa clipper", None), ("juice mission", None),
        ("europa", ["jupiter", "júpiter", "clipper", "moon", "mond", "lune", "luna", "ice", "eis",
                    "glace", "hielo", "ocean", "océan", "océano", "nasa", "jovian", "satellit", "gelo"]),
        ("europe", ["jupiter", "clipper", "lune", "moon"]),
        ("木卫二", None), ("木衛二", None), ("エウロパ", None), ("유로파", None),
        ("европа", ["юпитер", "клиппер", "спутник", "океан"]),
    ]),
    ("enceladus", "Enceladus", [
        ("enceladus", None), ("encelade", None), ("encelado", None), ("encélado", None), ("enceladu", None),
        ("orbilander", None), ("энцелад", None), ("土卫二", None), ("土衛二", None),
        ("エンケラド", None), ("엔셀라두스", None), ("إنسيلادوس", None), ("एन्सेलेडस", None),
    ]),
    ("k2-18b", "K2-18 b", [
        ("k2-18", None), ("k2 18", None), ("dimethyl sulfide", None), ("dimethyl sulphide", None),
        ("diméthylsulfure", None), ("dimetilsulfuro", None), ("dimetil sulfeto", None),
        ("dimethylsulfid", None), ("диметилсульфид", None), ("硫化二甲基", None),
        ("hycean", None), ("hycéan", None), ("hyceano", None),
    ]),
    ("titan", "Titan", [
        ("dragonfly", ["titan", "nasa", "saturn", "mission"]),
        ("titan", ["saturn", "saturne", "saturno", "moon", "lune", "luna", "mond", "methane",
                   "méthane", "metano", "lake", "mission", "dragonfly"]),
        ("титан", ["сатурн", "спутник"]), ("土卫六", None), ("タイタン", ["土星", "衛星"]),
    ]),
    ("venus", "Venus", [
        ("phosphine", None), ("fosfina", None), ("phosphin", None), ("фосфин", None), ("ホスフィン", None),
        ("venus", ["phosphine", "cloud", "life", "atmosphere", "fosfina", "vida", "leben", "vie",
                   "probe", "davinci", "veritas", "nube"]),
        ("金星", ["生命", "ホスフィン", "大気", "生物"]),
    ]),
    ("exoplanet*", "Exoplanets", [
        ("exoplanet*", None), ("exoplanète*", None), ("exoplaneta*", None), ("esopianeta", None),
        ("exoplaneet", None), ("egzoplaneta", None), ("экзопланет", None), ("екзопланет", None),
        ("系外行星", None), ("太陽系外惑星", None), ("외계행성", None), ("ötegezegen", None),
        ("eksoplanet", None), ("बाह्यग्रह", None), ("trappist-1", None), ("proxima b", None),
        ("habitable zone", None), ("zone habitable", None), ("zona habitable", None),
        ("ariel mission", None), ("plato mission", None), ("habitable worlds observatory", None),
    ]),
    ("seti", "SETI & technosignatures", [
        ("technosignature*", None), ("tecnofirma", None), ("технsignature", None),
        ("seti", ["alien", "signal", "institute", "radio", "search", "extraterrestrial",
                  "institut", "señal", "sinal", "сигнал"]),
        ("breakthrough listen", None), ("wow signal", None), ("allen telescope array", None),
    ]),
    ("method", "Detection methods", [
        ("biosignature*", None), ("biosignatur*", None), ("biofirma", None), ("bioseñal", None),
        ("bioassinatura", None), ("биосигнатур", None), ("バイオシグネチャー", None),
        ("生物特征", None), ("생물징후", None),
        ("astrobiolog*", None), ("exobiolog*", None), ("astrobiyoloji", None), ("астробиолог", None),
        ("астробіолог", None), ("宇宙生物学", None), ("天体生物学", None), ("天體生物學", None),
        ("우주생물학", None), ("ชีวดาราศาสตร์", None), ("علم الأحياء الفلكي", None),
        ("extremophile*", None), ("panspermia", None), ("prebiotic chemistry", None),
        ("origin of life", ["space", "astro", "planet", "cosmic", "ocean", "hydrothermal"]),
    ]),
]

# --------------------------------------------------------------------------
# The gate.  A story is kept only if it is about the search for life, not
# about space in general.  Two ways in:
#
#   CORE      — the subject is life beyond Earth on its own terms.  Keeps.
#   CONTEXT   — a body, mission or object that MIGHT be about life
#               (Mars, Europa, an exoplanet, a plume).  Keeps only when a
#               LIFE word appears with it.
#
# So "Roman telescope will image exoplanets" is dropped, "could there be life
# in helium atmospheres on exoplanets" is kept.  BLOCK removes UFO lore,
# astrology and the film franchise, which otherwise ride in on "alien life".
# --------------------------------------------------------------------------
CORE = [
    "biosignature*", "biosignatur*", "biofirma", "bioseñal", "bioassinatura", "биосигнатур",
    "バイオシグネチャー", "生物特征", "生物標誌", "생물징후", "بصمة حيوية",
    "astrobiolog*", "exobiolog*", "astrobiyoloji", "астробиолог", "астробіолог", "astrobiologi",
    "astrobiologia", "astrobiologie", "astrobiología", "宇宙生物学", "天体生物学", "天體生物學",
    "우주생물학", "ชีวดาราศาสตร์", "علم الأحياء الفلكي", "खगोल जीवविज्ञान",
    "extraterrestrial life", "alien life", "life beyond earth", "life elsewhere in the universe",
    "vida extraterrestre", "vie extraterrestre", "außerirdisches leben", "ausserirdisches leben",
    "vita extraterrestre", "vida fora da terra", "внеземн", "позаземн", "地球外生命", "外星生命",
    "地外生命", "외계 생명", "외계생명", "حياة خارج الأرض", "حیات فرازمینی", "परग्रही जीवन",
    "ভিনগ্রহের প্রাণ", "kehidupan luar angkasa", "dünya dışı yaşam", "buitenaards leven",
    "życie pozaziemskie", "utomjordiskt liv", "sự sống ngoài trái đất", "สิ่งมีชีวิตนอกโลก",
    "uhai nje ya dunia", "εξωγήινη ζωή", "חיים מחוץ לכדור הארץ",
    "technosignature*", "tecnofirma", "technosignatur", "seti institute", "breakthrough listen",
    "allen telescope array", "search for extraterrestrial intelligence",
    "panspermia", "panspermie", "lithopanspermia", "extremophile*", "extremófil*", "extremophil*",
    "prebiotic chemistry", "chimie prébiotique", "química prebiótica", "präbiotische chemie",
    "origin of life", "origine de la vie", "origen de la vida", "origem da vida",
    "ursprung des lebens", "происхождение жизни", "生命の起源", "生命起源", "생명의 기원",
    "habitability", "habitabilité", "habitabilidad", "habitabilidade", "abitabilità",
    "bewohnbarkeit", "обитаемост", "宜居性", "居住可能性",
    "habitable zone", "zone habitable", "zona habitable", "zona abitabile", "habitable Zone",
    "habitable world", "monde habitable", "mundo habitable", "ocean world", "monde océan",
    "mundo oceánico", "ozeanwelt", "mondo oceanico", "океанический мир",
    "mars sample return", "europa clipper", "enceladus orbilander", "dimethyl sulfide",
    "dimethyl sulphide", "diméthylsulfure", "dimetilsulfuro", "dimethylsulfid", "диметилсульфид",
    "hycean", "hycéan", "k2-18",
]

# Ocean worlds and the named biosignature targets.  These are only in the news
# because of the habitability question, so they keep on their own — but each
# carries an astronomical guard, because Enceladus is also a racehorse and a
# Chinese TV serial, and Europa is a continent and a football tournament.
ASTRO_GUARD = [
    "nasa", "esa", "jaxa", "cassini", "clipper", "juice", "spacecraft", "probe", "orbiter",
    "flyby", "mission", "moon", "moons", "saturn", "jupiter", "ocean", "ice", "icy", "plume",
    "geyser", "cryovolcan*", "hydrothermal", "astronom*", "planetary", "telescope",
    "lune", "luna", "lua", "mond", "maan", "księżyc", "satélite", "satellite", "спутник",
    "saturne", "saturno", "júpiter", "jupiter", "giove", "сатурн", "юпитер",
    "土星", "木星", "衛星", "探査", "탐사", "위성", "قمر", "زحل", "المشتري", "فضاء",
    "océan", "océano", "oceano", "oceanico", "ozean", "океан", "海洋", "바다", "महासागर",
    "hielo", "glace", "gelo", "ghiacc*", "ghiacciato", "banquise", "lunar", "lunaire",
    "sonda", "misión", "missione", "missão", "missie", "raumsonde", "espace", "espacio",
    "espaço", "spazio", "weltraum", "космос", "宇宙",
]

TARGETS = [
    ("enceladus", ASTRO_GUARD), ("encelade", ASTRO_GUARD), ("encelado", ASTRO_GUARD),
    ("encélado", ASTRO_GUARD), ("энцелад", ASTRO_GUARD), ("土卫二", ASTRO_GUARD),
    ("土衛二", ASTRO_GUARD), ("エンケラド", ASTRO_GUARD), ("엔셀라두스", ASTRO_GUARD),
    ("إنسيلادوس", ASTRO_GUARD), ("एन्सेलेडस", ASTRO_GUARD),
    ("europa", ASTRO_GUARD), ("エウロパ", ASTRO_GUARD), ("木卫二", ASTRO_GUARD),
    ("木衛二", ASTRO_GUARD), ("유로파", ASTRO_GUARD),
    ("titan", ["saturn", "saturne", "saturno", "dragonfly", "methane", "méthane", "metano",
               "lake", "lac", "土星", "衛星", "сатурн", "moon", "lune", "luna"]),
    ("титан", ["сатурн", "спутник"]), ("土卫六", None), ("タイタン", ["土星", "衛星"]),
    ("k2-18", None), ("k2 18", None), ("hycean", None),
    ("tiger stripes", None), ("tygrysie pasy", None), ("tigerstreifen", None),
    ("тигровые полосы", None), ("strisce tigrate", None), ("bandes de tigre", None),
    ("cheyava", None), ("jezero", None), ("mars sample return", None),
    ("dimethyl sulfide", None), ("dimethyl sulphide", None),
]

# Everything else that MIGHT be about life — kept only alongside a LIFE word.
WEAK = [
    "mars", "marte", "martian*", "martien*", "火星", "화성", "марс", "المريخ", "मंगल",
    "perseverance", "curiosity rover", "exomars", "tianwen",
    "venus", "vénus", "金星", "phosphine", "fosfina", "фосфин", "ホスフィン",
    "exoplanet*", "exoplanète*", "exoplaneta*", "esopianeta", "exoplaneet", "egzoplaneta",
    "экзопланет", "екзопланет", "系外行星", "太陽系外惑星", "외계행성", "ötegezegen",
    "eksoplanet", "बाह्यग्रह", "trappist-1", "proxima b", "super-earth", "super-terre",
    "supertierra", "subsurface ocean", "océan sous-glaciaire", "océano subsuperficial",
    "plume", "panache", "penacho", "羽流", "cryovolcan*", "hydrothermal",
    "organic molecule", "molécules organiques", "moléculas orgánicas", "organics",
    "有機分子", "유기 분자", "amino acid", "acides aminés", "aminoácido", "aminosäure",
    "アミノ酸", "아미노산", "methane", "méthane", "metano", "メタン", "메탄",
    "interstellar comet", "comet*", "comète", "cometa", "meteorite*", "météorite", "meteorito",
]

LIFE = [
    "life", "living", "alive", "biolog*", "microb*", "microorganism*", "micro-organism*",
    "bacteri*", "dna", "rna", "metabolis*", "photosynth*", "fossil",
    "habitab*", "inhabit*", "biosign*", "biomarker", "organic*", "prebiotic*", "amino acid",
    "vie", "vivant", "biologi*", "vida", "viva", "vita", "leben", "lebens", "bewohnbar",
    "жизн", "биолог", "микроб", "обитаем", "生命", "生物", "微生物", "有機", "宜居",
    "생명", "생물", "유기", "حياة", "حيوي", "أحياء", "حیات", "जीवन", "जैव", "প্রাণ",
    "hayat", "yaşam", "kehidupan", "hidup", "liv", "livet", "życie", "ζωή", "βιολογ",
    "sự sống", "sinh vật", "ชีวิต", "uhai", "חיים", "ביולוג", "habitável", "habitabil*",
]

BLOCK = [
    "ufo", "u.f.o", "ovni", "uap sighting", "unidentified flying", "unidentified aerial",
    "flying saucer", "roswell", "area 51", "abduction", "alien invasion", "alien: earth",
    "alien romulus", "xenomorph", "box office", "horoscope", "astrolog*", "астролог",
    "zodiac", "tarot", "conspiracy", "теория заговора", "占星",
    "europa league", "champions league", "conference league", "europa conference",
    # funding notices, calls and other administrative traffic on institutional feeds
    "cooperative agreement notice", "request for information", "call for papers",
    "call for proposals", "proposals due", "workshop registration", "abstract deadline",
    "job opening", "postdoctoral position", "now accepting applications",
    "explained in telugu", "explained in hindi", "in tamil |", "full episode",
]


# --------------------------------------------------------------------------
# Matching.  A bare substring test lets "view" satisfy the French word for
# life and "titanium" satisfy Titan, which is how orbit-navigation stories got
# into an astrobiology feed.  Latin-script terms are therefore matched on word
# edges; a trailing * matches the whole word family (astrobiolog* covers
# astrobiology, astrobiologist, astrobiological).  Terms in scripts without
# word breaks — Chinese, Japanese, Thai — stay substring matches.
# --------------------------------------------------------------------------
def _compile(term):
    if any(ord(ch) > 0x24F for ch in term):        # non-Latin script
        # substring matching is already prefix-like in scripts without word
        # breaks, so a trailing * is a no-op — strip it rather than search for
        # a literal asterisk, which is what used to happen.
        return term[:-1] if term.endswith("*") else term
    if term.endswith("*"):
        return re.compile(r"(?<![a-z0-9])" + re.escape(term[:-1]) + r"[a-z0-9\-]*", re.I)
    return re.compile(r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])", re.I)


def _compile_all(terms):
    return [_compile(t) for t in terms]


def hit(text, compiled):
    """True when any compiled term matches."""
    for c in compiled:
        if isinstance(c, str):
            if c in text:
                return True
        elif c.search(text):
            return True
    return False


CORE_C = _compile_all(CORE)
WEAK_C = _compile_all(WEAK)
LIFE_C = _compile_all(LIFE)
BLOCK_C = _compile_all(BLOCK)
TARGETS_C = [(_compile(t), _compile_all(g) if g else None) for t, g in TARGETS]
TOPICS_C = [(tid, label, [(_compile(t), _compile_all(g) if g else None) for t, g in terms])
            for tid, label, terms in TOPICS]

TAG_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"\s+")
PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)


# ----------------------------------------------------------------- fetching
def build_gnews_url(loc):
    q = loc["query"] + " when:30d"
    return ("https://news.google.com/rss/search?q=" + urllib.parse.quote(q) +
            "&hl=" + loc["hl"] + "&gl=" + loc["gl"] + "&ceid=" + loc["ceid"])


def load_sources():
    with open(SOURCES_PATH, encoding="utf-8") as fh:
        cfg = json.load(fh)
    srcs = []
    for s in cfg.get("direct", []):
        srcs.append({
            "name": s["name"], "lang": s["lang"], "region": s["region"],
            "kind": s.get("kind", "news"), "url": s["url"], "strict": s.get("strict", False),
        })
    for loc in cfg.get("gnews", []):
        srcs.append({
            "name": "Google News · " + loc["label"], "lang": loc["lang"],
            "lang_label": loc["label"], "region": loc["region"], "kind": "news",
            "url": build_gnews_url(loc),
        })
    return srcs, cfg


def fetch(url, tries=3):
    last = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/rss+xml, application/atom+xml, application/xml;q=0.9, */*;q=0.8",
                "Accept-Encoding": "gzip",
                "Accept-Language": "*",
            })
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                raw = resp.read()
                if resp.headers.get("Content-Encoding") == "gzip":
                    raw = gzip.GzipFile(fileobj=io.BytesIO(raw)).read()
                return raw
        except Exception as exc:                       # noqa: BLE001 — report, don't crash the run
            last = exc
            time.sleep(1.5 * (attempt + 1))
    print("  ! unreachable: %s (%s)" % (url[:90], last), file=sys.stderr)
    return None


# ----------------------------------------------------------------- parsing
def strip_ns(tag):
    return tag.split("}", 1)[1] if "}" in tag else tag


def text_of(el):
    return WS_RE.sub(" ", html.unescape(TAG_RE.sub(" ", el.text or ""))).strip() if el is not None else ""


def child(node, *names):
    for kid in node:
        if strip_ns(kid.tag) in names:
            return kid
    return None


def parse_date(raw):
    if not raw:
        return None
    raw = raw.strip()
    try:
        dt = parsedate_to_datetime(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp() * 1000)
    except Exception:  # noqa: BLE001
        pass
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp() * 1000)
    except Exception:  # noqa: BLE001
        return None


def parse_feed(raw, src):
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        # Some publishers serve a stray byte before the declaration.
        try:
            root = ET.fromstring(raw[raw.index(b"<"):])
        except Exception:  # noqa: BLE001
            return []

    nodes = [n for n in root.iter() if strip_ns(n.tag) == "item"]
    atom = False
    if not nodes:
        nodes = [n for n in root.iter() if strip_ns(n.tag) == "entry"]
        atom = True

    out = []
    for n in nodes:
        title = text_of(child(n, "title"))
        if atom:
            link = ""
            for kid in n:
                if strip_ns(kid.tag) == "link" and kid.get("rel", "alternate") == "alternate":
                    link = kid.get("href", "")
                    break
        else:
            link_el = child(n, "link")
            link = (link_el.text or "").strip() if link_el is not None else ""
            if not link:
                link = text_of(child(n, "guid"))
        if not title or not link:
            continue

        outlet_el = child(n, "source")
        outlet = text_of(outlet_el) if outlet_el is not None else ""
        if outlet and title.endswith(" - " + outlet):
            title = title[: -(len(outlet) + 3)].strip()
        elif not outlet and src["name"].startswith("Google News") and " - " in title:
            # Google News appends the outlet to the headline when it omits <source>.
            head, _, tail = title.rpartition(" - ")
            if head and 2 <= len(tail) <= 45:
                title, outlet = head.strip(), tail.strip()

        stamp = parse_date(text_of(child(n, "pubDate", "published", "updated", "date")))
        snippet = text_of(child(n, "description", "summary", "content"))[:SNIPPET_CHARS]

        out.append({
            "t": title,
            "u": link,
            "o": outlet or src["name"].replace("Google News · ", ""),
            "g": src["lang"],
            "r": src["region"],
            "k": src.get("kind", "news"),
            "d": stamp,
            "s": snippet,
            "w": src["name"],
        })
    return out


# ------------------------------------------------------------- classifying
def topics_for(text):
    hits = []
    for tid, _label, terms in TOPICS_C:
        for term, guards in terms:
            if not hit(text, [term]):
                continue
            if guards and not hit(text, guards):
                continue
            hits.append(tid)
            break
    return hits


def relevant(text, strict=False):
    """CORE alone keeps a story.  A named biosignature target keeps on its own.
    Anything weaker keeps only alongside a LIFE word — and on a `strict` source
    (a general space desk) a LIFE word is required either way."""
    if hit(text, BLOCK_C):
        return False
    if hit(text, CORE_C):
        return True
    named = any(hit(text, [term]) for term, _g in TARGETS_C)
    guarded = any(hit(text, [term]) and (not guards or hit(text, guards))
                  for term, guards in TARGETS_C)
    weak = hit(text, WEAK_C)
    life = hit(text, LIFE_C)
    if strict:
        # A general space desk has to say what it is about: naming a body is not
        # enough on its own, a life word has to be there too.
        return (named or weak) and life
    # A guarded target keeps by itself — Enceladus beside Saturn, ice or a plume
    # is only ever the ocean-world story.  A bare mention keeps only with a life
    # word, which is what separates the moon from the racehorse of the same name.
    return guarded or ((named or weak) and life)


def fingerprint(title):
    norm = PUNCT_RE.sub(" ", title.lower())
    return " ".join(WS_RE.sub(" ", norm).strip().split()[:9])


def canon_url(url):
    try:
        parts = urllib.parse.urlsplit(url)
        query = urllib.parse.parse_qsl(parts.query)
        query = [(k, v) for k, v in query if not k.lower().startswith("utm_")]
        return urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/"),
                                        urllib.parse.urlencode(query), ""))
    except Exception:  # noqa: BLE001
        return url


# ------------------------------------------------------------------- main
def run(dry_run=False, fixtures=None):
    sources, cfg = load_sources()
    print("Reading %d wires…" % len(sources))

    def read(src):
        if fixtures:
            path = os.path.join(fixtures, re.sub(r"[^\w.-]", "_", src["name"]) + ".xml")
            if not os.path.exists(path):
                return src, None
            with open(path, "rb") as fh:
                return src, fh.read()
        return src, fetch(src["url"])

    results = []
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for src, raw in pool.map(read, sources):
            results.append((src, raw))

    # Carry forward what previous runs already collected, so the feed has depth
    # beyond whatever happens to sit in a 30-day RSS window today.
    previous = []
    if os.path.exists(OUT_PATH):
        try:
            with open(OUT_PATH, encoding="utf-8") as fh:
                previous = json.load(fh).get("items", [])
        except Exception:  # noqa: BLE001
            previous = []

    seen_fp, seen_url, items = set(), set(), []

    def absorb(row):
        fp = fingerprint(row["t"])
        cu = canon_url(row["u"])
        if fp in seen_fp or cu in seen_url:
            return False
        seen_fp.add(fp)
        seen_url.add(cu)
        items.append(row)
        return True

    stats, ok_count = [], 0
    for src, raw in results:
        stat = {"name": src["name"], "lang": src["lang"], "region": src["region"], "kept": 0, "ok": False}
        if raw:
            stat["ok"] = True
            ok_count += 1
            for row in parse_feed(raw, src):
                text = (row["t"] + " " + row["s"]).lower()
                if not relevant(text, src.get("strict", False)):
                    continue
                row["x"] = topics_for(text) or ["method"]
                if absorb(row):
                    stat["kept"] += 1
        stats.append(stat)
        print("  %-34s %s" % (src["name"][:34], "unreachable" if not raw else "%d kept" % stat["kept"]))

    fresh_urls = {canon_url(i["u"]) for i in items}
    for row in previous:
        if "x" not in row:
            continue
        absorb(row)

    cutoff = int(time.time() * 1000) - RETAIN_DAYS * 86400000
    items = [i for i in items if (i.get("d") or cutoff + 1) >= cutoff]
    items.sort(key=lambda i: i.get("d") or 0, reverse=True)
    items = items[:MAX_ITEMS]
    fresh = sum(1 for i in items if canon_url(i["u"]) in fresh_urls)

    languages = {}
    for loc in cfg.get("gnews", []):
        languages.setdefault(loc["lang"], re.sub(r"\s*·.*$|\s*\(.*$|\s+\d+$", "", loc["label"]).strip())
    languages.setdefault("en", "English")

    payload = {
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "counts": {
            "stories": len(items),
            "new_this_run": fresh,
            "languages": len({i["g"] for i in items}),
            "wires_ok": ok_count,
            "wires_total": len(sources),
        },
        "languages": languages,
        "topics": [{"id": tid, "label": label} for tid, label, _ in TOPICS],
        "sources": stats,
        "items": items,
    }

    print("\n%d stories (%d new this run) · %d languages · %d/%d wires answered"
          % (len(items), fresh, payload["counts"]["languages"], ok_count, len(sources)))
    zero = [s["name"] for s in stats if s["ok"] and s["kept"] == 0]
    if zero:
        print("Answered but returned nothing on topic: " + ", ".join(zero))

    if dry_run:
        print("\n--dry-run: wire.json not written")
        return payload

    with open(OUT_PATH, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, separators=(",", ":"))
    print("Wrote %s (%.0f KB)" % (OUT_PATH, os.path.getsize(OUT_PATH) / 1024))
    return payload


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="harvest and report, write nothing")
    ap.add_argument("--fixtures", help="read *.xml from this directory instead of the network")
    args = ap.parse_args()
    run(dry_run=args.dry_run, fixtures=args.fixtures)
