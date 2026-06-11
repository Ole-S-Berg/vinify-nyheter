#!/usr/bin/env python3
"""
Vinmonopolet + Systembolaget Nyhetsrapport
==========================================
Henter nye produkter fra Vinmonopolet og/eller Systembolaget og
genererer en kombinert HTML-rapport med ettertraktedhet-score.

Bruk:
    python vinmonopolet_nyheter.py              # Siste 30 dager (standard)
    python vinmonopolet_nyheter.py --dager 7    # Kun siste 7 dager

Konfigurer i vinmonopolet_config.json:
  - api_nokkel             : Vinmonopolet API-nøkkel (påkrevd)
  - systembolaget_api_nokkel: Systembolaget API-nøkkel (valgfritt)

API-nøkler:
  Vinmonopolet : https://api.vinmonopolet.no
  Systembolaget: https://api-portal.systembolaget.se
"""

import json
import sys
import argparse
import datetime
import re
import unicodedata
import urllib.request
import urllib.parse
import urllib.error
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
CONFIG_FILE = SCRIPT_DIR / "vinmonopolet_config.json"
RAPPORT_DIR = SCRIPT_DIR / "rapporter"

DEFAULT_CONFIG = {
    "api_nokkel": "DIN_API_NOKKEL_HER",
    "systembolaget_api_nokkel": "",
    "filtre": {
        "ekskluder_navn": [
            "pose", "glass", "tilbehor", "tilbehør", "kork", "brett",
            "kasse", "box", "bag", "kartong", "gaveeske", "samlepakke"
        ]
    },
    "rapport": {
        "tittel": "Vinmonopolet + Systembolaget – Nyheter",
        "antall_dager_tilbake": 30
    }
}

VM_BASE_URL = "https://apis.vinmonopolet.no"
SB_BASE_URL = "https://api-extern.systembolaget.se"

# API-nøkkel som Systembolaget bruker i sin egen nettside (offentlig tilgjengelig)
SB_DEFAULT_KEY = "cfc702aed3094c86b92d6d4ff7a54c84"

# ── Ettertraktedhet-score ──────────────────────────────────────────────────────

HYPE_ORD = {
    # ── NIVÅ 5: Ikonisk / Legendarisk ─────────────────────────────────────────
    "romanee": 5, "romanée": 5, "la romanee": 5, "romanee-conti": 5,
    "drc": 5, "domaine de la romanee": 5,
    "petrus": 5, "le pin": 5, "lafleur": 5,
    "screaming eagle": 5, "harlan": 5, "scarecrow": 5, "opus one": 5,
    "penfolds grange": 5, "grange": 5,
    "vega sicilia unico": 5, "unico": 5,
    "pingus": 5,
    "sassicaia": 5, "masseto": 5, "ornellaia": 5, "solaia": 5,
    "giacomo conterno": 5, "bartolo mascarello": 5,
    "leroy": 5, "domaine leroy": 5,
    "roumier": 5, "rousseau": 5, "dujac": 5, "roulot": 5,
    "coche-dury": 5, "leflaive": 5, "ramonet": 5,
    "yquem": 5, "d'yquem": 5,
    "jayer": 5, "henri jayer": 5,
    "gaja": 5,
    "zind-humbrecht": 5, "egon müller": 5, "egon muller": 5,

    # ── NIVÅ 4: Høyt ettertraktet ──────────────────────────────────────────────
    "grand cru": 4, "premier cru": 4, "1er cru": 4,
    "musigny": 4, "chambertin": 4, "montrachet": 4, "corton": 4,
    "richebourg": 4, "echezeaux": 4, "échézeaux": 4,
    "clos de vougeot": 4, "bonnes mares": 4, "la tache": 4,
    "petite chapelle": 4, "mazis": 4, "charmes": 4,
    "chevalier-montrachet": 4, "batard-montrachet": 4, "bâtard": 4,
    "haut-brion": 4, "la mission": 4, "pape clement": 4,
    "cheval blanc": 4, "ausone": 4, "angelus": 4, "angélus": 4,
    "pavie": 4, "figeac": 4,
    "latour": 4, "lafite": 4, "mouton": 4, "margaux": 4,
    "leoville": 4, "léoville": 4, "pichon": 4, "ducru": 4,
    "cos d'estournel": 4, "montrose": 4, "lynch-bages": 4,
    "hermitage": 4, "côte rôtie": 4, "cote rotie": 4,
    "condrieu": 4, "chave": 4, "jaboulet": 4, "chapoutier": 4,
    "guigal la landonne": 4, "guigal la mouline": 4, "guigal la turque": 4,
    "vintage champagne": 4, "prestige cuvee": 4, "prestige cuvée": 4,
    "cristal": 4, "dom perignon": 4, "dom pérignon": 4,
    "krug": 4, "salon": 4, "belle epoque": 4, "belle époque": 4,
    "comtes de champagne": 4,
    "barolo riserva": 4, "barbaresco riserva": 4,
    "brunello riserva": 4, "brunello di montalcino": 4,
    "amarone della valpolicella": 4,
    "quinta do noval nacional": 4, "graham's ne oublie": 4,
    "vintage port": 4,
    "penfolds bin": 4, "hill of grace": 4,
    "caymus special selection": 4, "ridge monte bello": 4,

    # ── NIVÅ 3: Ettertraktet ───────────────────────────────────────────────────
    "barolo": 3, "barbaresco": 3, "brunello": 3, "amarone": 3,
    "sforzato": 3, "sfursat": 3,
    "bourgogne blanc": 3, "bourgogne rouge": 3,
    "gevrey-chambertin": 3, "vosne-romanée": 3, "vosne-romanee": 3,
    "chambolle-musigny": 3, "morey-saint-denis": 3,
    "nuits-saint-georges": 3, "pommard": 3, "volnay": 3,
    "puligny-montrachet": 3, "chassagne-montrachet": 3, "meursault": 3,
    "corton-charlemagne": 3,
    "chateauneuf": 3, "châteauneuf": 3, "châteauneuf-du-pape": 3,
    "rayas": 3, "château rayas": 3, "beaucastel": 3,
    "pegau": 3, "pégau": 3,
    "saint-joseph": 3, "cornas": 3,
    "priorat": 3, "ribera del duero reserva": 3, "rioja gran reserva": 3,
    "vega sicilia": 3, "abadia retuerta": 3,
    "tokaji aszú": 3, "tokaji aszu": 3, "tokaji eszencia": 3,
    "sauternes": 3, "barsac": 3,
    "mosel spätlese": 3, "mosel auslese": 3,
    "trockenbeerenauslese": 3, "beerenauslese": 3, "eiswein": 3,
    "chablis premier cru": 3, "chablis grand cru": 3,
    "lapierre": 3, "foillard": 3, "thevenet": 3,
    "dard et ribo": 3, "dard & ribo": 3,
    "overnoy": 3, "ganevat": 3, "tissot": 3,
    "gravner": 3, "radikon": 3,
    "frank cornelissen": 3, "cornelissen": 3,
    "silent stills": 3, "lost distillery": 3,
    "old & rare": 3, "old and rare": 3,
    "single cask": 3, "cask strength": 3,
    "port ellen": 3, "brora": 3, "rosebank": 3,

    # ── NIVÅ 2: Bemerkelsesverdig ──────────────────────────────────────────────
    "champagne": 2,
    "bourgogne": 2, "burgundy": 2, "chablis": 2,
    "bordeaux": 2, "pauillac": 2, "saint-julien": 2,
    "saint-estephe": 2, "saint-émilion": 2, "saint emilion": 2,
    "graves": 2, "pessac-léognan": 2,
    "rhone": 2, "rhône": 2, "crozes-hermitage": 2,
    "gigondas": 2, "vacqueyras": 2,
    "mosel": 2, "rheingau": 2, "rheinhessen": 2, "pfalz": 2, "nahe": 2,
    "riesling": 2, "grüner veltliner": 2, "gruner veltliner": 2,
    "wachau": 2, "kamptal": 2, "kremstal": 2,
    "alsace": 2,
    "rioja reserva": 2, "ribera del duero": 2,
    "penedes": 2, "rias baixas": 2,
    "chianti classico": 2, "valpolicella": 2,
    "etna": 2, "nerello mascalese": 2,
    "fiano": 2, "greco di tufo": 2,
    "napa valley": 2, "sonoma coast": 2, "anderson valley": 2,
    "willamette valley": 2, "sta. rita hills": 2,
    "tokaji": 2, "madeira": 2, "jerez": 2,
    "jura": 2, "beaujolais": 2, "morgon": 2, "moulin-à-vent": 2,
    "fleurie": 2, "saint-amour": 2, "chiroubles": 2,
    "loire": 2, "sancerre": 2, "pouilly-fumé": 2,
    "muscadet": 2, "vouvray": 2, "savennières": 2,
    "chinon": 2, "bourgueil": 2,
    "old malt cask": 2, "gordon & macphail": 2, "signatory": 2,
    "berry bros": 2, "cadenhead": 2,
    "springbank": 2, "glenfarclas": 2, "highland park": 2,
    "ardbeg": 2, "laphroaig": 2, "lagavulin": 2,

    # ── NIVÅ 1: Interessant ────────────────────────────────────────────────────
    "reserva": 1, "reserve": 1, "riserva": 1, "gran reserva": 1,
    "classico": 1, "superiore": 1, "superieur": 1,
    "vieilles vignes": 1, "old vine": 1, "old vines": 1,
    "cru": 1,
    "kabinett": 1, "spätlese": 1, "auslese": 1,
    "blanc de blancs": 1, "blanc de noirs": 1,
    "pinot noir": 1, "nebbiolo": 1, "sangiovese": 1,
    "syrah": 1, "grenache": 1, "mourvèdre": 1, "mourvedre": 1,
    "tempranillo": 1, "garnacha": 1,
    "chardonnay": 1, "sauvignon blanc": 1,
    "gewürztraminer": 1, "gewurztraminer": 1,
    "malbec": 1, "carmenere": 1, "cabernet franc": 1,
    "nero d'avola": 1, "aglianico": 1,
    "sherry": 1, "manzanilla": 1, "amontillado": 1, "palo cortado": 1,
    "vintage": 1,
}


def hype_nivaa(score: int) -> tuple:
    if score >= 8:
        return ("🏆 Ikonisk", "#581c87")
    elif score >= 5:
        return ("🔥 Høyt ettertraktet", "#7c2d12")
    elif score >= 3:
        return ("⭐ Ettertraktet", "#92400e")
    elif score >= 1:
        return ("Interessant", "#1d4ed8")
    else:
        return ("", "#6b7280")


def score_produkt(navn: str) -> int:
    navn_lower = navn.lower()
    score = 0
    for ord_str, verdi in HYPE_ORD.items():
        if ord_str in navn_lower:
            score += verdi
    return score


def er_relevant(navn: str, ekskluder: list) -> bool:
    navn_lower = navn.lower()
    return not any(e in navn_lower for e in ekskluder)


# ── Vinmonopolet ──────────────────────────────────────────────────────────────

def hent_vm_produkter(api_nokkel: str, endret_siden: datetime.date) -> list:
    alle = []
    start = 0
    batch = 500
    print(f"  Henter fra Vinmonopolet API (siden {endret_siden})...")

    while True:
        params = {
            "maxResults": batch,
            "start": start,
            "changedSince": endret_siden.strftime("%Y-%m-%d"),
        }
        url = f"{VM_BASE_URL}/products/v0/details-normal?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers={
            "Ocp-Apim-Subscription-Key": api_nokkel,
            "User-Agent": "curl/8.7.1",
            "Accept": "*/*",
        })
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 401:
                print("\nFEIL: Ugyldig Vinmonopolet API-nøkkel.")
                sys.exit(1)
            raise
        if not data:
            break
        alle.extend(data)
        print(f"    {len(alle)} produkter (Vinmonopolet)...")
        if len(data) < batch:
            break
        start += batch

    return alle


def _vm_extract_meta(p: dict) -> dict:
    """Henter ut pris, størrelse, stil m.m. fra Vinmonopolet API-respons."""
    pris = 0.0
    try:
        priser = p.get("prices", [])
        if priser:
            pris = float(priser[0].get("salesPrice", 0))
        if not pris:
            pris = float(p.get("basic", {}).get("price", 0))
    except (TypeError, ValueError):
        pris = 0.0

    storrelse = 0.75
    try:
        props = p.get("properties", {})
        bs = props.get("bottleSize", None)
        if bs is None:
            priser = p.get("prices", [])
            if priser:
                bs = priser[0].get("bottleSize", {})
        if isinstance(bs, dict):
            storrelse = float(bs.get("value", 0.75))
        elif isinstance(bs, (int, float)):
            storrelse = float(bs)
    except (TypeError, ValueError):
        storrelse = 0.75

    stil = ""
    try:
        mc = p.get("classification", {}).get("mainCategory", {})
        stil = mc.get("name", "") if isinstance(mc, dict) else ""
    except (TypeError, AttributeError):
        stil = ""

    understil = ""
    try:
        sc = p.get("classification", {}).get("mainSubCategory", {})
        understil = sc.get("name", "") if isinstance(sc, dict) else ""
    except (TypeError, AttributeError):
        understil = ""

    argang = ""
    try:
        yr = p.get("properties", {}).get("year", "")
        if yr:
            argang = str(int(float(yr)))
    except (TypeError, ValueError):
        argang = ""

    land = ""
    try:
        origins = p.get("origins", [])
        if origins:
            land = origins[0].get("country", {}).get("name", "")
        if not land:
            land = p.get("classification", {}).get("origin", {}).get("name", "")
    except (TypeError, AttributeError):
        land = ""

    return {
        "pris": pris,
        "storrelse": round(storrelse, 3),
        "stil": stil,
        "understil": understil,
        "argang": argang,
        "land": land,
    }


def normaliser_vm(p: dict, ekskluder: list):
    navn = p["basic"]["productShortName"]
    if not er_relevant(navn, ekskluder):
        return None
    score = score_produkt(navn)
    meta = _vm_extract_meta(p)
    produkt_id = p["basic"]["productId"]
    return {
        "_kilde": "vinmonopolet",
        "_score": score,
        "_id": str(produkt_id),
        "_navn": navn,
        "_pris": meta["pris"],
        "_pris_valuta": "kr",
        "_url": f"https://www.vinmonopolet.no/p/{produkt_id}",
        "_bilde_url": f"https://bilder.vinmonopolet.no/cache/515x515-0/{produkt_id}-1.jpg",
        "_dato": p["lastChanged"]["date"],
        "_storrelse": meta["storrelse"],
        "_stil": meta["stil"],
        "_understil": meta["understil"],
        "_argang": meta["argang"],
        "_land": meta["land"],
        "_kommende": False,
    }


# ── Systembolaget ─────────────────────────────────────────────────────────────

def hent_sb_produkter(api_nokkel: str, endret_siden: datetime.date) -> list:
    alle = []
    page = 1
    size = 30
    print(f"  Henter fra Systembolaget API (siden {endret_siden})...")

    while True:
        params = {
            "page": page,
            "size": size,
            "sortBy": "productLaunchDate",
            "sortDirection": "Descending",
        }
        url = f"{SB_BASE_URL}/sb-api-ecommerce/v1/productsearch/search?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers={
            "Ocp-Apim-Subscription-Key": api_nokkel,
            "User-Agent": "curl/8.7.1",
            "Accept": "application/json",
        })
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read().decode("utf-8")
                data = json.loads(raw)
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8")[:300]
            except Exception:
                pass
            if e.code == 401:
                print("\nFEIL: Ugyldig Systembolaget API-nøkkel.")
                return []
            print(f"\nFEIL Systembolaget API {e.code}: {body}")
            return alle

        # Respons kan være enten en liste eller {products: [...]}
        if isinstance(data, list):
            products = data
        else:
            products = data.get("products", [])


        if not products:
            break

        gone_past = False
        for p in products:
            launch_str = (p.get("productLaunchDate", "") or "")[:10]
            if launch_str:
                try:
                    launch = datetime.date.fromisoformat(launch_str)
                    if launch < endret_siden:
                        gone_past = True
                        break
                except ValueError:
                    pass
            alle.append(p)

        print(f"    {len(alle)} produkter (Systembolaget)...")
        if gone_past or len(products) < size:
            break
        page += 1

    return alle


def hent_sb_kommende(api_nokkel: str, maks_dager: int = 90) -> list:
    """Henter kommende Systembolaget-lanseringer (fremtidige produktLaunchDate)."""
    alle = []
    page = 1
    size = 30
    i_dag = datetime.date.today()
    frist = i_dag + datetime.timedelta(days=maks_dager)
    print(f"  Henter kommende Systembolaget-lanseringer (neste {maks_dager} dager)...")

    while True:
        params = {
            "page": page,
            "size": size,
            "sortBy": "productLaunchDate",
            "sortDirection": "Descending",
        }
        url = f"{SB_BASE_URL}/sb-api-ecommerce/v1/productsearch/search?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers={
            "Ocp-Apim-Subscription-Key": api_nokkel,
            "User-Agent": "curl/8.7.1",
            "Accept": "application/json",
        })
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read().decode("utf-8")
                data = json.loads(raw)
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8")[:300]
            except Exception:
                pass
            print(f"\nFEIL Systembolaget kommende {e.code}: {body}")
            return alle

        products = data if isinstance(data, list) else data.get("products", [])
        if not products:
            break

        gone_past_window = False
        for p in products:
            launch_str = (p.get("productLaunchDate", "") or "")[:10]
            if not launch_str:
                continue
            try:
                launch = datetime.date.fromisoformat(launch_str)
            except ValueError:
                continue
            if launch > frist:
                continue   # for langt frem i tid
            if launch <= i_dag:
                return alle  # forbi i dag – stopp paginering
            alle.append(p)

        print(f"    {len(alle)} kommende produkter (Systembolaget)...")
        if gone_past_window or len(products) < size:
            break
        page += 1

    return alle


def _sb_kategori_slug(kategori: str) -> str:
    """Mapper Systembolaget-kategori til top-level URL-slug (slik systembolaget.se bruker det)."""
    k = kategori.lower().strip()
    # Alt som er vin bruker "vin" i URL (ikke rott-vin, vitt-vin osv.)
    if any(w in k for w in ("vin", "rosé", "rose", "mousserande", "sake")):
        return "vin"
    mapping = {
        "öl": "ol", "sprit": "sprit", "cider": "cider",
        "blanddrycker": "blanddrycker", "alkoholfritt": "alkoholfritt",
    }
    for key, slug in mapping.items():
        if key in k:
            return slug
    return "produkt"


def _sb_namn_slug(namn: str) -> str:
    """Konverterer produktnavn til URL-slug (systembolaget.se-format)."""
    s = namn.lower()
    # Tegn som ikke dekomponeres automatisk
    for src, dst in [("æ", "a"), ("œ", "o"), ("ø", "o"), ("ß", "ss")]:
        s = s.replace(src, dst)
    # Dekomponerer å->a, ä->a, ö->o, é->e osv.
    normalized = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in normalized if not unicodedata.combining(c))
    slug = re.sub(r"[^\w\s-]", "", s)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug


def normaliser_sb(p: dict, ekskluder: list):
    bold = (p.get("productNameBold", "") or "").strip()
    thin = (p.get("productNameThin", "") or "").strip()
    navn = f"{bold} {thin}".strip() if thin else bold
    if not navn:
        return None
    if not er_relevant(navn, ekskluder):
        return None

    score = score_produkt(navn)

    # productId = intern ID (brukes i bilde-CDN)
    # productNumber = 7-sifret artikkelnummer (brukes i produkt-URL)
    product_id = str(p.get("productId", "") or "").strip()
    product_number = str(p.get("productNumber", "") or "").strip()
    url_id = product_number or product_id  # foretrekk productNumber for URL

    pris = float(p.get("price", 0) or 0)
    volum_ml = float(p.get("volume", 750) or 750)
    storrelse = round(volum_ml / 1000, 3)

    stil = (p.get("categoryLevel1", "") or "").strip()
    understil = (p.get("categoryLevel2", "") or "").strip()

    argang = str(p.get("vintage", "") or "").strip()
    if argang in ("0", "0000", "None", ""):
        argang = ""

    dato_str = (p.get("productLaunchDate", "") or "")[:10]
    dato = dato_str

    land = (p.get("country", "") or "").strip()

    # Kommende = lansert i fremtiden, eller merket som weblaunch
    kommende = False
    if dato_str:
        try:
            launch = datetime.date.fromisoformat(dato_str)
            kommende = launch > datetime.date.today()
        except ValueError:
            pass
    if p.get("isWebLaunch", False):
        kommende = True

    # Systembolaget image CDN bruker intern productId
    bilde_url = (
        f"https://product-cdn.systembolaget.se/productimages/{product_id}/{product_id}_400.jpg"
        if product_id else ""
    )
    # Produkt-URL: systembolaget.se/produkt/{kategori}/{navn-slug}-{productNumber}/
    kat_slug = _sb_kategori_slug(stil)
    namn_slug = _sb_namn_slug(navn) if navn else ""
    url = (
        f"https://www.systembolaget.se/produkt/{kat_slug}/{namn_slug}-{url_id}/"
        if url_id else "#"
    )

    return {
        "_kilde": "systembolaget",
        "_score": score,
        "_id": product_id,
        "_navn": navn,
        "_pris": pris,
        "_pris_valuta": "kr (SEK)",
        "_url": url,
        "_bilde_url": bilde_url,
        "_dato": dato,
        "_storrelse": storrelse,
        "_stil": stil,
        "_understil": understil,
        "_argang": argang,
        "_land": land,
        "_kommende": kommende,
    }


# ── HTML-generering ───────────────────────────────────────────────────────────

def lag_produktkort(p: dict) -> str:
    kilde = p.get("_kilde", "vinmonopolet")
    score = p.get("_score", 0)
    navn = p.get("_navn", "")
    pris = p.get("_pris", 0)
    pris_valuta = p.get("_pris_valuta", "kr")
    url = p.get("_url", "#")
    bilde_url = p.get("_bilde_url", "")
    dato = p.get("_dato", "")
    storrelse = p.get("_storrelse", 0.75)
    stil = p.get("_stil", "")
    understil = p.get("_understil", "")
    argang = p.get("_argang", "")
    land = p.get("_land", "")
    kommende = "1" if p.get("_kommende") else "0"

    etikett, badge_farge = hype_nivaa(score)
    hype_html = (
        f'<span class="hype-badge" style="background:{badge_farge}">{etikett}</span>'
        if etikett else ''
    )

    if kilde == "vinmonopolet":
        kilde_html = '<span class="kilde-badge kilde-vm">🇳🇴 Vinmonopolet</span>'
        lenke_tekst = "Se på Vinmonopolet →"
    else:
        kilde_html = '<span class="kilde-badge kilde-sb">🇸🇪 Systembolaget</span>'
        lenke_tekst = "Se på Systembolaget →"

    kommende_html = '<span class="kommende-badge">🗓 Kommende</span>' if kommende == "1" else ""

    meta_deler = []
    if argang:
        meta_deler.append(f'<span class="meta-argang">{argang}</span>')
    if pris:
        pris_fmt = f"{pris:,.0f}".replace(",", " ") + f" {pris_valuta}"
        meta_deler.append(f'<span class="meta-pris">{pris_fmt}</span>')
    meta_html = (
        f'<div class="produkt-meta">{"".join(meta_deler)}</div>'
        if meta_deler else ''
    )

    return f"""
<div class="kort" data-score="{score}" data-dato="{dato}"
     data-storrelse="{storrelse}" data-stil="{stil}"
     data-understil="{understil}" data-argang="{argang}"
     data-kilde="{kilde}" data-land="{land}"
     data-kommende="{kommende}" data-pris="{pris}">
  <div class="kort-indre">
    <img src="{bilde_url}" alt="{navn}"
         onerror="this.style.display='none'"
         class="produktbilde">
    <div class="kort-info">
      <div class="kort-topp">
        {kilde_html}
        {kommende_html}
        {hype_html}
        <span class="endret-dato">{dato}</span>
      </div>
      <h3 class="produktnavn">
        <a href="{url}" target="_blank">{navn}</a>
      </h3>
      {meta_html}
      <div class="pris-rad">
        <a href="{url}" class="kilde-lenke" target="_blank">{lenke_tekst}</a>
      </div>
    </div>
  </div>
</div>"""


def lag_html_rapport(produkter: list, dato_fra: datetime.date, tittel: str,
                     har_vm: bool, har_sb: bool) -> str:
    dato_str = datetime.date.today().strftime("%d.%m.%Y")
    i_dag = datetime.date.today().isoformat()
    antall_dager_hentet = (datetime.date.today() - dato_fra).days
    kort_html = "\n".join(lag_produktkort(p) for p in produkter)

    vm_count = sum(1 for p in produkter if p.get("_kilde") == "vinmonopolet")
    sb_count = sum(1 for p in produkter if p.get("_kilde") == "systembolaget")

    # Stats
    stats_html = f"""
    <div class="stat"><strong id="stat-total">{len(produkter)}</strong>Totalt</div>
    <div class="stat"><strong>{sum(1 for p in produkter if p.get('_score',0) >= 3)}</strong>Ettertraktet+</div>
    <div class="stat"><strong>{sum(1 for p in produkter if p.get('_score',0) >= 5)}</strong>Høyt ettertraktet+</div>
    <div class="stat"><strong>{sum(1 for p in produkter if p.get('_score',0) >= 8)}</strong>Ikonisk</div>"""

    if har_vm and har_sb:
        stats_html += f"""
    <div class="stat stat-sep"><strong>{vm_count}</strong>🇳🇴 Vinmonopolet</div>
    <div class="stat"><strong>{sb_count}</strong>🇸🇪 Systembolaget</div>"""

    # Kilde-filteret vises bare når begge kilder er tilgjengelige
    kilde_filter_html = ""
    if har_vm and har_sb:
        kilde_filter_html = """
  <div class="kontroll-gruppe">
    <label>Kilde:</label>
    <div class="kilde-knapper">
      <button class="kilde-btn aktiv" data-kilde="">Alle</button>
      <button class="kilde-btn kilde-btn-vm" data-kilde="vinmonopolet">🇳🇴 Vinmonopolet</button>
      <button class="kilde-btn kilde-btn-sb" data-kilde="systembolaget">🇸🇪 Systembolaget</button>
    </div>
  </div>"""

    nullstill_kilde_js = "aktivKilde = ''; document.querySelectorAll('.kilde-btn').forEach(b => b.classList.toggle('aktiv', b.dataset.kilde === ''));" if har_vm and har_sb else ""

    return f"""<!DOCTYPE html>
<html lang="no">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{tittel}</title>
<style>
  :root {{
    --bg: #fafaf8; --kort-bg: #fff;
    --tekst: #1a1a1a; --dempet: #6b7280;
    --border: #e5e7eb; --accent: #7c2d12; --lys: #fef3e8;
    --sb-grønn: #166534;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: Georgia, serif; background: var(--bg); color: var(--tekst); }}
  header {{ background: var(--accent); color: white; padding: 1.6rem 2rem 1.3rem; }}
  header h1 {{ font-size: 1.6rem; font-weight: normal; }}
  .undertittel {{ font-size: .82rem; opacity: .8; margin-top: .25rem; font-family: sans-serif; }}
  .stats {{ margin-top: .85rem; display: flex; gap: 2rem; font-family: sans-serif; font-size: .8rem; flex-wrap: wrap; align-items: flex-end; }}
  .stat strong {{ font-size: 1.25rem; display: block; font-family: Georgia, serif; }}
  .stat-sep {{ border-left: 1px solid rgba(255,255,255,.3); padding-left: 2rem; }}
  .kontroller {{
    background: white; border-bottom: 1px solid var(--border);
    padding: .85rem 2rem; display: flex; align-items: center;
    gap: 1.8rem; flex-wrap: wrap; font-family: sans-serif; font-size: .84rem;
    position: sticky; top: 0; z-index: 10; box-shadow: 0 1px 4px rgba(0,0,0,.06);
  }}
  .kontroll-gruppe {{ display: flex; align-items: center; gap: .5rem; }}
  .kontroll-gruppe label {{ font-weight: 600; color: #374151; white-space: nowrap; }}
  .sok {{
    padding: .38rem .7rem; border: 1px solid var(--border);
    border-radius: 4px; font-size: .84rem; width: 200px;
  }}
  input[type=range] {{ accent-color: var(--accent); }}
  .slider-verdi {{ color: var(--accent); font-weight: bold; min-width: 2.2rem; }}
  .nullstill-btn {{
    font-size: .78rem; padding: .3rem .75rem;
    border: 1px solid var(--border); border-radius: 4px;
    background: var(--lys); color: var(--accent); cursor: pointer;
    margin-left: auto;
  }}
  .nullstill-btn:hover {{ background: #fde8d0; }}
  .hoved {{ padding: 1rem 2rem 2rem; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(340px, 1fr)); gap: 1rem; }}
  .kort {{
    background: var(--kort-bg); border: 1px solid var(--border);
    border-radius: 8px; overflow: hidden;
    transition: box-shadow .15s, border-color .15s;
  }}
  .kort:hover {{ box-shadow: 0 4px 16px rgba(0,0,0,.08); border-color: #d1d5db; }}
  .kort-indre {{ display: flex; }}
  .produktbilde {{
    width: 82px; min-width: 82px; height: 115px;
    object-fit: contain; background: #f9f5f0;
    border-right: 1px solid var(--border); padding: 4px;
  }}
  .kort-info {{ padding: .8rem .9rem; flex: 1; min-width: 0; }}
  .kort-topp {{ display: flex; align-items: center; gap: .4rem; margin-bottom: .3rem; flex-wrap: wrap; }}
  .hype-badge {{
    color: white; font-size: .65rem; font-weight: bold;
    padding: 2px 8px; border-radius: 3px;
    font-family: sans-serif; letter-spacing: .02em; white-space: nowrap;
  }}
  .kilde-badge {{
    font-size: .65rem; font-weight: 700; padding: 2px 7px; border-radius: 3px;
    font-family: sans-serif; letter-spacing: .02em; white-space: nowrap;
  }}
  .kilde-vm {{ background: #fef3c7; color: #92400e; }}
  .kilde-sb {{ background: #dcfce7; color: var(--sb-grønn); }}
  .kommende-badge {{
    font-size: .65rem; font-weight: 700; padding: 2px 7px; border-radius: 3px;
    background: #e0e7ff; color: #3730a3;
    font-family: sans-serif; letter-spacing: .02em; white-space: nowrap;
  }}
  .kommende-label {{ display: flex; align-items: center; gap: .4rem; cursor: pointer; }}
  .endret-dato {{ font-size: .7rem; color: var(--dempet); font-family: sans-serif; }}
  .produktnavn {{ font-size: .95rem; line-height: 1.35; margin-bottom: .45rem; }}
  .produktnavn a {{ color: var(--tekst); text-decoration: none; }}
  .produktnavn a:hover {{ color: var(--accent); text-decoration: underline; }}
  .pris-rad {{ display: flex; align-items: center; margin-top: .3rem; }}
  .kilde-lenke {{
    font-size: .74rem; color: var(--accent);
    text-decoration: none; font-family: sans-serif;
  }}
  .kilde-lenke:hover {{ text-decoration: underline; }}
  .produkt-meta {{
    display: flex; gap: .6rem; align-items: center;
    margin-bottom: .35rem; font-family: sans-serif;
  }}
  .meta-argang {{
    font-size: .75rem; font-weight: 600;
    background: #f3f0eb; color: #4b3f35;
    padding: 1px 7px; border-radius: 3px; letter-spacing: .02em;
  }}
  .meta-pris {{
    font-size: .8rem; font-weight: 700; color: var(--accent); font-family: sans-serif;
  }}
  .filter-select {{
    padding: .3rem .55rem; border: 1px solid var(--border);
    border-radius: 4px; font-size: .82rem;
    background: white; color: #374151; cursor: pointer; max-width: 140px;
  }}
  .filter-select:focus {{ outline: 2px solid var(--accent); outline-offset: 1px; }}
  .kilde-knapper {{ display: flex; gap: .3rem; }}
  .kilde-btn {{
    padding: .28rem .75rem; border: 1px solid var(--border);
    border-radius: 20px; font-size: .78rem; cursor: pointer;
    background: white; color: #374151; transition: all .15s;
    font-family: sans-serif; white-space: nowrap;
  }}
  .kilde-btn:hover {{ border-color: #9ca3af; background: #f9fafb; }}
  .kilde-btn.aktiv {{ background: var(--accent); color: white; border-color: var(--accent); }}
  .kilde-btn-sb.aktiv {{ background: var(--sb-grønn); border-color: var(--sb-grønn); }}
  .ingen-treff {{ text-align: center; padding: 4rem; color: var(--dempet); font-family: sans-serif; }}
  #synlige-info {{ font-family: sans-serif; font-size: .8rem; color: var(--dempet); }}
</style>
</head>
<body>
<header>
  <h1>{tittel}</h1>
  <p class="undertittel">Siste {antall_dager_hentet} dager · Generert {dato_str}</p>
  <div class="stats">{stats_html}
    <div style="margin-left:auto"><span id="synlige-info" style="color:rgba(255,255,255,.7)"></span></div>
  </div>
</header>

<div class="kontroller">
  <div class="kontroll-gruppe">
    <label>Søk:</label>
    <input type="text" class="sok" id="sok" placeholder="navn, region, produsent...">
  </div>
  <div class="kontroll-gruppe">
    <label>Siste:</label>
    <input type="range" id="dager-slider" min="1" max="{antall_dager_hentet}" step="1"
           value="{antall_dager_hentet}" style="width:100px">
    <span class="slider-verdi"><span id="dager-verdi">{antall_dager_hentet}</span> dager</span>
  </div>
  <div class="kontroll-gruppe">
    <label>Min. ettertraktet:</label>
    <input type="range" id="hype-slider" min="0" max="8" step="1" value="0" style="width:80px">
    <span class="slider-verdi" id="hype-verdi-vis">Alle</span>
  </div>
  <div class="kontroll-gruppe">
    <label>Størrelse:</label>
    <select id="storrelse-filter" class="filter-select">
      <option value="0.75" selected>0,75 l</option>
      <option value="">Alle</option>
      <option value="0.187">0,187 l</option>
      <option value="0.375">0,375 l</option>
      <option value="0.5">0,5 l</option>
      <option value="1.0">1,0 l</option>
      <option value="1.5">1,5 l</option>
      <option value="3.0">3,0 l</option>
    </select>
  </div>
  <div class="kontroll-gruppe">
    <label>Kategori:</label>
    <select id="stil-filter" class="filter-select">
      <option value="">Alle</option>
    </select>
  </div>
  <div class="kontroll-gruppe">
    <label>Underkategori:</label>
    <select id="understil-filter" class="filter-select">
      <option value="">Alle</option>
    </select>
  </div>
  <div class="kontroll-gruppe">
    <label>Årgang:</label>
    <select id="argang-filter" class="filter-select">
      <option value="">Alle</option>
    </select>
  </div>
  <div class="kontroll-gruppe">
    <label>Land:</label>
    <select id="land-filter" class="filter-select">
      <option value="">Alle</option>
    </select>
  </div>
  <div class="kontroll-gruppe">
    <label>Pris (maks):</label>
    <div class="slider-wrap">
      <input type="range" id="pris-slider" min="0" max="5000" step="50" value="5000">
      <span id="pris-verdi-vis">Alle</span>
    </div>
  </div>
  <div class="kontroll-gruppe">
    <label class="kommende-label">
      <input type="checkbox" id="kommende-filter">
      Kun kommende 🇸🇪
    </label>
  </div>{kilde_filter_html}
  <button class="nullstill-btn" onclick="nullstill()">Nullstill</button>
</div>

<main class="hoved">
  <div class="grid" id="grid">{kort_html}</div>
  <p class="ingen-treff" id="ingen" style="display:none">Ingen produkter matcher filtrene.</p>
</main>

<script>
const kort = Array.from(document.querySelectorAll('.kort'));
const iDag = new Date('{i_dag}');
let aktivKilde = '';

const HYPE_ETIKETTER = {{
  0: 'Alle', 1: 'Interessant (1+)', 3: 'Ettertraktet (3+)',
  5: 'Høyt ettertraktet (5+)', 8: 'Ikonisk (8+)',
}};

function byggDropdowns() {{
  const stilMap = {{}};
  const arganger = new Set();
  const land = new Set();
  let maxPris = 0;
  kort.forEach(k => {{
    const s = k.dataset.stil || '';
    const u = k.dataset.understil || '';
    const a = k.dataset.argang || '';
    const l = k.dataset.land || '';
    const pris = parseFloat(k.dataset.pris || 0);
    if (s) {{
      if (!stilMap[s]) stilMap[s] = new Set();
      if (u) stilMap[s].add(u);
    }}
    if (a) arganger.add(a);
    if (l) land.add(l);
    if (pris > maxPris) maxPris = pris;
  }});
  const stilSel = document.getElementById('stil-filter');
  Object.keys(stilMap).sort().forEach(s => {{
    const o = document.createElement('option');
    o.value = s; o.textContent = s; stilSel.appendChild(o);
  }});
  stilSel.addEventListener('change', () => {{ oppdaterUnderstil(stilMap); oppdater(); }});
  const argSel = document.getElementById('argang-filter');
  Array.from(arganger).sort((a, b) => b - a).forEach(y => {{
    const o = document.createElement('option');
    o.value = y; o.textContent = y; argSel.appendChild(o);
  }});
  const landSel = document.getElementById('land-filter');
  Array.from(land).sort().forEach(l => {{
    const o = document.createElement('option');
    o.value = l; o.textContent = l; landSel.appendChild(o);
  }});
  const prisSlider = document.getElementById('pris-slider');
  const avrundet = Math.ceil(maxPris / 50) * 50;
  prisSlider.max = avrundet;
  prisSlider.value = avrundet;
}}

function oppdaterUnderstil(stilMap) {{
  const valgt = document.getElementById('stil-filter').value;
  const sel = document.getElementById('understil-filter');
  sel.innerHTML = '<option value="">Alle</option>';
  if (valgt && stilMap[valgt]) {{
    Array.from(stilMap[valgt]).sort().forEach(u => {{
      const o = document.createElement('option');
      o.value = u; o.textContent = u; sel.appendChild(o);
    }});
  }}
}}

function oppdater() {{
  const soek = document.getElementById('sok').value.toLowerCase();
  const maxDager = parseInt(document.getElementById('dager-slider').value);
  const minHype = parseInt(document.getElementById('hype-slider').value);
  const stilFilter = document.getElementById('stil-filter').value;
  const understilFilter = document.getElementById('understil-filter').value;
  const argangFilter = document.getElementById('argang-filter').value;
  const stoerrelseFilter = document.getElementById('storrelse-filter').value;
  const landFilter = document.getElementById('land-filter').value;
  const maxPris = parseInt(document.getElementById('pris-slider').value);
  const sliderMax = parseInt(document.getElementById('pris-slider').max);
  const kunKommende = document.getElementById('kommende-filter').checked;
  const grenseDato = new Date(iDag);
  grenseDato.setDate(grenseDato.getDate() - maxDager);

  let synlige = 0;
  kort.forEach(k => {{
    const produktPris = parseFloat(k.dataset.pris || 0);
    const vises =
      k.querySelector('.produktnavn').innerText.toLowerCase().includes(soek)
      && parseInt(k.dataset.score || 0) >= minHype
      && new Date(k.dataset.dato) >= grenseDato
      && (!stilFilter || k.dataset.stil === stilFilter)
      && (!understilFilter || k.dataset.understil === understilFilter)
      && (!argangFilter || k.dataset.argang === argangFilter)
      && (!stoerrelseFilter || Math.abs(parseFloat(k.dataset.storrelse||0.75) - parseFloat(stoerrelseFilter)) < 0.001)
      && (!landFilter || k.dataset.land === landFilter)
      && (maxPris >= sliderMax || produktPris === 0 || produktPris <= maxPris)
      && (!kunKommende || k.dataset.kommende === '1')
      && (!aktivKilde || k.dataset.kilde === aktivKilde);
    k.style.display = vises ? '' : 'none';
    if (vises) synlige++;
  }});

  document.getElementById('ingen').style.display = synlige ? 'none' : '';
  document.getElementById('grid').style.display = synlige ? '' : 'none';
  const info = synlige + ' produkt' + (synlige !== 1 ? 'er' : '') + ' vises';
  document.getElementById('synlige-info').textContent = info;
  const headerInfo = document.getElementById('stat-total');
  if (headerInfo) headerInfo.textContent = synlige;
}}

function nullstill() {{
  document.getElementById('sok').value = '';
  document.getElementById('dager-slider').value = {antall_dager_hentet};
  document.getElementById('dager-verdi').textContent = '{antall_dager_hentet}';
  document.getElementById('hype-slider').value = 0;
  document.getElementById('hype-verdi-vis').textContent = 'Alle';
  document.getElementById('storrelse-filter').value = '0.75';
  document.getElementById('stil-filter').value = '';
  document.getElementById('understil-filter').innerHTML = '<option value="">Alle</option>';
  document.getElementById('argang-filter').value = '';
  document.getElementById('land-filter').value = '';
  document.getElementById('pris-slider').value = document.getElementById('pris-slider').max;
  document.getElementById('pris-verdi-vis').textContent = 'Alle';
  document.getElementById('kommende-filter').checked = false;
  {nullstill_kilde_js}
  oppdater();
}}

document.getElementById('sok').addEventListener('input', oppdater);
document.getElementById('dager-slider').addEventListener('input', function() {{
  document.getElementById('dager-verdi').textContent = this.value;
  oppdater();
}});
document.getElementById('hype-slider').addEventListener('input', function() {{
  const v = parseInt(this.value);
  const snapped = [0,1,3,5,8].reduce((a,b) => Math.abs(b-v)<Math.abs(a-v)?b:a);
  document.getElementById('hype-verdi-vis').textContent = HYPE_ETIKETTER[snapped]||(v+'+');
  oppdater();
}});
document.getElementById('pris-slider').addEventListener('input', function() {{
  const v = parseInt(this.value);
  const max = parseInt(this.max);
  document.getElementById('pris-verdi-vis').textContent = v >= max ? 'Alle' : v + ' kr';
  oppdater();
}});
document.getElementById('kommende-filter').addEventListener('change', oppdater);
['storrelse-filter','understil-filter','argang-filter','land-filter'].forEach(id =>
  document.getElementById(id).addEventListener('change', oppdater)
);
document.querySelectorAll('.kilde-btn').forEach(btn => {{
  btn.addEventListener('click', function() {{
    document.querySelectorAll('.kilde-btn').forEach(b => b.classList.remove('aktiv'));
    this.classList.add('aktiv');
    aktivKilde = this.dataset.kilde;
    oppdater();
  }});
}});

byggDropdowns();
oppdater();
</script>
</body>
</html>"""


# ── Hoved ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Vinmonopolet + Systembolaget Nyhetsrapport")
    parser.add_argument("--dager", type=int, default=None)
    parser.add_argument("--vm-key", default=None, help="Vinmonopolet API-nøkkel (overstyrer config)")
    parser.add_argument("--sb-key", default=None, help="Systembolaget API-nøkkel (overstyrer config)")
    parser.add_argument("--output", default=None, help="Sti for HTML-rapport (overstyrer standard rapporter/-mappe)")
    args = parser.parse_args()

    print("\n🍷 Vinmonopolet + Systembolaget Nyhetsrapport")
    print("=" * 45)

    if not CONFIG_FILE.exists():
        CONFIG_FILE.write_text(json.dumps(DEFAULT_CONFIG, ensure_ascii=False, indent=2))
        print("Konfigurasjonsfil opprettet. Legg inn API-nøkkel i vinmonopolet_config.json")
        sys.exit(0)

    config = {}
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, encoding="utf-8") as f:
            config = json.load(f)

    # CLI-argumenter overstyrer config
    vm_nokkel = args.vm_key or config.get("api_nokkel", "")
    if not vm_nokkel or vm_nokkel == "DIN_API_NOKKEL_HER":
        print("FEIL: Legg inn Vinmonopolet API-nøkkel (--vm-key eller vinmonopolet_config.json)")
        sys.exit(1)

    dager = args.dager or config.get("rapport", {}).get("antall_dager_tilbake", 30)
    dato_fra = datetime.date.today() - datetime.timedelta(days=dager)
    ekskluder = [e.lower() for e in config.get("filtre", {}).get("ekskluder_navn", [])]

    alle_produkter = []

    # Vinmonopolet
    har_vm = bool(vm_nokkel)
    if har_vm:
        vm_raw = hent_vm_produkter(vm_nokkel, dato_fra)
        print(f"  {len(vm_raw)} produkter hentet fra Vinmonopolet")
        for p in vm_raw:
            norm = normaliser_vm(p, ekskluder)
            if norm:
                alle_produkter.append(norm)

    # Systembolaget – bruker standard nøkkel hvis ingen er oppgitt
    sb_nokkel = args.sb_key or config.get("systembolaget_api_nokkel", "").strip() or SB_DEFAULT_KEY
    har_sb = True
    if har_sb:
        sb_raw = hent_sb_produkter(sb_nokkel, dato_fra)
        print(f"  {len(sb_raw)} produkter hentet fra Systembolaget")
        for p in sb_raw:
            norm = normaliser_sb(p, ekskluder)
            if norm:
                alle_produkter.append(norm)

        # Kommende lanseringer (neste 90 dager)
        sb_kommende_raw = hent_sb_kommende(sb_nokkel, maks_dager=90)
        print(f"  {len(sb_kommende_raw)} kommende lanseringer hentet fra Systembolaget")
        sb_ids_sett = {p.get("_id") for p in alle_produkter if p["_kilde"] == "systembolaget"}
        for p in sb_kommende_raw:
            norm = normaliser_sb(p, ekskluder)
            if norm and norm["_id"] not in sb_ids_sett:
                norm["_kommende"] = True
                alle_produkter.append(norm)
                sb_ids_sett.add(norm["_id"])

    # Sorter: høyest score øverst, deretter nyeste dato
    alle_produkter.sort(key=lambda p: (-p.get("_score", 0), p.get("_dato", "")))

    vm_count = sum(1 for p in alle_produkter if p["_kilde"] == "vinmonopolet")
    sb_count = sum(1 for p in alle_produkter if p["_kilde"] == "systembolaget")
    ikoniske = sum(1 for p in alle_produkter if p.get("_score", 0) >= 8)
    hoyt = sum(1 for p in alle_produkter if p.get("_score", 0) >= 5)
    etterspurt = sum(1 for p in alle_produkter if p.get("_score", 0) >= 3)

    print(f"\n  Totalt: {len(alle_produkter)} produkter etter filter")
    if har_vm:
        print(f"  🇳🇴 Vinmonopolet: {vm_count}")
    if har_sb:
        print(f"  🇸🇪 Systembolaget: {sb_count}")
    print(f"  Ikonisk: {ikoniske} · Høyt ettertraktet: {hoyt} · Ettertraktet: {etterspurt}")

    dato_str = datetime.date.today().strftime("%Y-%m-%d")
    tittel = config.get("rapport", {}).get("tittel", "Vinmonopolet & Systembolaget Nyheter")

    if args.output:
        rapport_fil = Path(args.output)
        rapport_fil.parent.mkdir(parents=True, exist_ok=True)
    else:
        RAPPORT_DIR.mkdir(exist_ok=True)
        rapport_fil = RAPPORT_DIR / f"nyheter_{dato_str}.html"

    html = lag_html_rapport(alle_produkter, dato_fra, tittel, har_vm, har_sb)
    rapport_fil.write_text(html, encoding="utf-8")

    print(f"\nRapport: {rapport_fil}")
    if not args.output:
        import webbrowser
        webbrowser.open(rapport_fil.as_uri())
        print("  Åpner i nettleser...")


if __name__ == "__main__":
    main()
