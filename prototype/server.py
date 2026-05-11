#!/usr/bin/env python3
"""
MTL PropIntel — Local Backend Server
=====================================
Run:  python3 server.py
Then: python3 -m http.server 3000
Open: http://localhost:3000/montreal-propintel.html
"""

import csv
import io
import json
import math
import re
import sqlite3
import urllib.request
import urllib.parse
import zipfile
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

PORT     = 8000
DATA_DIR = Path(__file__).parent / "propintel_data"
DB_PATH  = DATA_DIR / "properties.db"

SOURCES = {
    "assessment": {
        "url":  "https://donnees.montreal.ca/fr/dataset/4ad6baea-4d2c-460f-a8bf-5d000db498f7/resource/2b9dfc3d-91d3-48de-b32c-a2a6d9417079/download/uniteevaluationfonciere.csv",
        "path": DATA_DIR / "uniteevaluationfonciere.csv",
        "desc": "Assessment roll CSV (~72MB)",
    },
    "permits": {
        "url":  "https://donnees.montreal.ca/dataset/d90eaf1b-2de8-43f0-923a-27a620ecdf41/resource/5232a72d-235a-48eb-ae20-bb9d501300ad/download/permis-construction.csv",
        "path": DATA_DIR / "permis-construction.csv",
        "desc": "Building permits CSV",
    },
    "contaminated": {
        "url":  "https://ville.montreal.qc.ca/pls/portal/PORTALCON.TERRAINS_CONTAMINES_DATA.LISTE",
        "path": DATA_DIR / "terrains-contamines.json",
        "desc": "Contaminated sites JSON",
    },
    "stm_gtfs": {
        "url":  "https://www.stm.info/sites/default/files/gtfs/gtfs_stm.zip",
        "path": DATA_DIR / "gtfs_stm.zip",
        "desc": "STM GTFS feed (~20MB)",
    },
    "transactions_2023": {
        "url":  "https://donnees.montreal.ca/dataset/3c5d5ba3-5406-4bfe-a970-d799ecde4aea/resource/2f7a72a3-b941-43a6-943f-5a975dcf880c/download/liste-des-transactions-immobilieres.csv",
        "path": DATA_DIR / "transactions_2023.csv",
        "desc": "Real estate transactions 2023 CSV",
    },
    "transactions_2024": {
        "url":  "https://donnees.montreal.ca/dataset/3c5d5ba3-5406-4bfe-a970-d799ecde4aea/resource/615c52d7-a8f3-4d7b-a274-bc6ca9c843a5/download/liste-des-transactions-2024.csv",
        "path": DATA_DIR / "transactions_2024.csv",
        "desc": "Real estate transactions 2024 CSV",
    },
    "geocoder_geojson": {
        "url":  None,  # fetched at runtime via resource_show — URL is signed and expires
        "path": DATA_DIR / "adresses.geojson",
        "resource_id": "d3f65ec7-57d0-44bc-858c-93e449dbdcbc",
        "desc": "Address points GeoJSON — all ~500k Montreal civic addresses with coordinates (134MB)",
    },
    "parks": {
        "url":  "https://donnees.montreal.ca/api/3/action/datastore_search?resource_id=35796624-15df-4503-a569-797665f8768e&limit=5000",
        "path": DATA_DIR / "espace_vert.csv",
        "desc": "Parks & green spaces CSV",
    },
    "commercial": {
        "url":  "https://donnees.montreal.ca/fr/dataset/f8582c4d-a933-4306-bb27-d883e13dd207/resource/fb2e534a-c573-45b5-b62b-8f99e3a37cd1/download/occupation-commerciale-2024.csv",
        "path": DATA_DIR / "locaux_commerciaux.csv",
        "desc": "Commercial premises CSV (2024 survey)",
    },
}

# CKAN live endpoints (no download needed — queried at runtime)
CKAN_BASE  = "https://donnees.montreal.ca/api/3/action"
# lieux-batiments-vocation-publique: fetch via direct CSV download (CKAN resource ID varies)
CKAN_FACILITIES_URL  = ""   # deprecated
CKAN_FACILITIES_ID   = "4731b64f-29cc-4e08-bc44-8752ae2fcafb"  # CSV French, confirmed 2026-05-03
CKAN_FACILITIES_PKGS = [
    "lieux-batiments-vocation-publique",
    "batiments-municipaux",
    "lieux-interet",
    "lieux-d-interet",
]
CKAN_POI_ID        = "edce22aa-f7cc-495e-9c53-b367f68309f6"  # lieux d'interet (points of interest)
CKAN_ADDR_ID       = "fed5fd02-5535-458e-b13f-66e7a31a6d78"  # adresses ponctuelles (geocoder)

REM_STATIONS = [
    {"name":"Brossard","lat":45.4453,"lng":-73.4598},
    {"name":"Panama","lat":45.4590,"lng":-73.4700},
    {"name":"Du Quartier","lat":45.4698,"lng":-73.4780},
    {"name":"Ile-des-Soeurs","lat":45.4812,"lng":-73.5178},
    {"name":"Gare Centrale","lat":45.4997,"lng":-73.5698},
    {"name":"McGill","lat":45.5043,"lng":-73.5706},
    {"name":"Edouard-Montpetit","lat":45.5042,"lng":-73.6152},
    {"name":"Canora","lat":45.5085,"lng":-73.6460},
    {"name":"Mont-Royal REM","lat":45.5217,"lng":-73.6250},
    {"name":"A-40","lat":45.5318,"lng":-73.6480},
    {"name":"Bois-Franc","lat":45.5368,"lng":-73.6795},
    {"name":"Sunnybrooke","lat":45.5393,"lng":-73.7023},
    {"name":"Roxboro-Pierrefonds","lat":45.5163,"lng":-73.8090},
    {"name":"Ile-Bigras","lat":45.5093,"lng":-73.8548},
    {"name":"Sainte-Dorothee","lat":45.5348,"lng":-73.8735},
    {"name":"Laval-sur-le-Lac","lat":45.5500,"lng":-73.8915},
    {"name":"Val-des-Brises","lat":45.5615,"lng":-73.9062},
    {"name":"Deux-Montagnes","lat":45.5300,"lng":-73.8900},
    {"name":"Des Sources","lat":45.4948,"lng":-73.7610},
    {"name":"Fairview-Pointe-Claire","lat":45.4868,"lng":-73.8025},
    {"name":"Kirkland","lat":45.4658,"lng":-73.8680},
    {"name":"Anse-a-l-Orme","lat":45.4453,"lng":-73.9268},
]

BOROUGH_CENTRES = {
    "Ahuntsic-Cartierville":(45.5575,-73.6717),
    "Anjou":(45.6017,-73.5600),
    "Cote-des-Neiges-Notre-Dame-de-Grace":(45.4879,-73.6262),
    "Le Plateau-Mont-Royal":(45.5231,-73.5793),
    "Le Sud-Ouest":(45.4740,-73.5782),
    "L'Ile-Bizard-Sainte-Genevieve":(45.5000,-73.8700),
    "Lachine":(45.4333,-73.6935),
    "LaSalle":(45.4333,-73.6345),
    "Mercier-Hochelaga-Maisonneuve":(45.5527,-73.5350),
    "Montreal-Nord":(45.5994,-73.6302),
    "Outremont":(45.5167,-73.6125),
    "Pierrefonds-Roxboro":(45.4976,-73.8248),
    "Riviere-des-Prairies-Pointe-aux-Trembles":(45.6240,-73.5430),
    "Rosemont-La Petite-Patrie":(45.5462,-73.5972),
    "Saint-Laurent":(45.5033,-73.6985),
    "Saint-Leonard":(45.5830,-73.5783),
    "Verdun":(45.4620,-73.5657),
    "Ville-Marie":(45.5088,-73.5632),
    "Villeray-Saint-Michel-Parc-Extension":(45.5453,-73.6292),
    "Westmount":(45.4818,-73.5993),
    "Mont-Royal":(45.5161,-73.6437),
    "Pointe-Claire":(45.4683,-73.8214),
    "Beaconsfield":(45.4333,-73.8667),
    "Dollard-Des-Ormeaux":(45.4904,-73.8120),
    "Kirkland":(45.4462,-73.8700),
    "Cote-Saint-Luc":(45.4667,-73.6667),
    "Dorval":(45.4500,-73.7500),
    "Hampstead":(45.4833,-73.6333),
}

# ── SOURCED MARKET BENCHMARKS ─────────────────────────────────────────────────
# All figures from verifiable public sources.
# Primary: QPAREB/Centris borough-level medians Q4 2025 + March 2026.
# Secondary: CMHC Montreal Rental Market Report 2024.
# Tertiary: Montreal assessment roll comparative factor 2026 (+12.2% vs 2023 roll).

# ── QPAREB Centris Q4 2025 median sale prices by borough and type ──────────────
# Source: QPAREB residential barometer Q4 2025, broker Centris database.
# All figures in CAD. "plex" = 2-5 units. "multi" = 6+ units (extrapolated).
QPAREB_MEDIANS = {
    # borough_norm → {type → median_price}
    "Le Plateau-Mont-Royal": {
        "condo":700000, "single_family":1300000, "plex":1220000, "multi":2800000},
    "Rosemont-La Petite-Patrie": {
        "condo":595000, "single_family":1155000, "plex":1022000, "multi":2200000},
    "Cote-des-Neiges-Notre-Dame-de-Grace": {
        "condo":606000, "single_family":1340000, "plex":1044000, "multi":2400000},
    "Ville-Marie": {
        "condo":630000, "single_family":1450000, "plex":1100000, "multi":3500000},
    "Outremont": {
        "condo":680000, "single_family":1800000, "plex":1400000, "multi":3200000},
    "Westmount": {
        "condo":750000, "single_family":2800000, "plex":1800000, "multi":4000000},
    "Le Sud-Ouest": {
        "condo":550000, "single_family":900000,  "plex":870000,  "multi":1900000},
    "Villeray-Saint-Michel-Parc-Extension": {
        "condo":545000, "single_family":711000,  "plex":901000,  "multi":1900000},
    "Mercier-Hochelaga-Maisonneuve": {
        "condo":430000, "single_family":680000,  "plex":750000,  "multi":1600000},
    "Verdun": {
        "condo":500000, "single_family":850000,  "plex":820000,  "multi":1800000},
    "Ahuntsic-Cartierville": {
        "condo":480000, "single_family":750000,  "plex":790000,  "multi":1700000},
    "Saint-Laurent": {
        "condo":450000, "single_family":700000,  "plex":730000,  "multi":1550000},
    "Saint-Leonard": {
        "condo":440000, "single_family":680000,  "plex":720000,  "multi":1500000},
    "Anjou": {
        "condo":420000, "single_family":640000,  "plex":680000,  "multi":1400000},
    "Lachine": {
        "condo":430000, "single_family":680000,  "plex":720000,  "multi":1550000},
    "LaSalle": {
        "condo":420000, "single_family":660000,  "plex":700000,  "multi":1500000},
    "Pierrefonds-Roxboro": {
        "condo":480000, "single_family":700000,  "plex":730000,  "multi":1500000},
    "Riviere-des-Prairies-Pointe-aux-Trembles": {
        "condo":430000, "single_family":625000,  "plex":670000,  "multi":1400000},
    "L-Ile-Bizard-Sainte-Genevieve": {
        "condo":450000, "single_family":780000,  "plex":750000,  "multi":1600000},
    "Montreal-Nord": {
        "condo":390000, "single_family":560000,  "plex":620000,  "multi":1300000},
    "Mont-Royal": {
        "condo":680000, "single_family":2200000, "plex":1600000, "multi":3500000},
    "Beaconsfield": {
        "condo":480000, "single_family":900000,  "plex":800000,  "multi":1700000},
    "Dollard-Des-Ormeaux": {
        "condo":460000, "single_family":780000,  "plex":750000,  "multi":1600000},
    "Kirkland": {
        "condo":470000, "single_family":850000,  "plex":780000,  "multi":1650000},
    "Pointe-Claire": {
        "condo":450000, "single_family":790000,  "plex":750000,  "multi":1600000},
    "Cote-Saint-Luc": {
        "condo":500000, "single_family":900000,  "plex":850000,  "multi":1800000},
    "Dorval": {
        "condo":440000, "single_family":730000,  "plex":730000,  "multi":1550000},
    # Island-wide fallback (March 2026 QPAREB)
    "_island": {
        "condo":544000, "single_family":652000,  "plex":924000,  "multi":1950000},
}

# ── CMHC Montreal 2024 average monthly rents ──────────────────────────────────
# Source: CMHC Rental Market Report, Montreal CMA, Fall 2024
# Weighted average assuming typical bedroom mix for income properties
CMHC_AVG_RENT_MONTHLY = {
    "Le Plateau-Mont-Royal": 1820,
    "Rosemont-La Petite-Patrie": 1680,
    "Cote-des-Neiges-Notre-Dame-de-Grace": 1650,
    "Ville-Marie": 1950,
    "Outremont": 1900,
    "Westmount": 2100,
    "Le Sud-Ouest": 1600,
    "Villeray-Saint-Michel-Parc-Extension": 1520,
    "Mercier-Hochelaga-Maisonneuve": 1420,
    "Verdun": 1580,
    "Ahuntsic-Cartierville": 1480,
    "Saint-Laurent": 1450,
    "_default": 1480,  # CMHC island-wide average 2024
}

# ── QPAREB cap rates 2024 (income properties) ─────────────────────────────────
# Source: QPAREB/JLR market reports 2024. Plex cap rates 4.5-6% on island.
QPAREB_CAP_RATES = {
    "Le Plateau-Mont-Royal": 4.5,
    "Rosemont-La Petite-Patrie": 4.8,
    "Outremont": 4.2,
    "Westmount": 3.9,
    "Mont-Royal": 4.0,
    "Ville-Marie": 4.3,
    "Cote-des-Neiges-Notre-Dame-de-Grace": 4.9,
    "Le Sud-Ouest": 5.1,
    "Verdun": 5.0,
    "Villeray-Saint-Michel-Parc-Extension": 5.3,
    "Mercier-Hochelaga-Maisonneuve": 5.4,
    "Ahuntsic-Cartierville": 5.2,
    "Saint-Laurent": 5.3,
    "Lachine": 5.5, "LaSalle": 5.4, "Saint-Leonard": 5.5,
    "Anjou": 5.6, "Montreal-Nord": 5.8,
    "_default": 5.2,
}

# In-memory market rate tables — populated by build_market_rates() from transactions CSV.
# These supplement and refine the QPAREB_MEDIANS above.
MARKET_RATES = {}
MARKET_RATES_LOADED = False
TRANSACTIONS_LOADED = 0

CUBF_LABELS = {
    1000:"Single-family",1001:"Single-family detached",1002:"Single-family semi-detached",
    1003:"Single-family row/townhouse",1010:"Duplex",1040:"Triplex",
    1090:"Plex (4-5 units)",1100:"Multi-residential (6+ units)",
    1210:"Seniors residence",2000:"Commercial",2010:"Retail",2020:"Office",
    3000:"Industrial",4000:"Institutional",5000:"Agricultural",
    6000:"Vacant land",9100:"Condo unit",9200:"Condo common",
}


# NO_ARROND_ILE_CUM codes → borough names (Montreal assessment roll)
# NO_ARROND_ILE_CUM codes (format "REM06", "REM19" etc., strip prefix → "6", "19")
ARROND_CODE_MAP = {
    # Arrondissements de Montréal (01–19)
    "1":"Ahuntsic-Cartierville","2":"Anjou",
    "3":"Cote-des-Neiges-Notre-Dame-de-Grace","4":"Lachine","5":"LaSalle",
    "6":"Le Plateau-Mont-Royal","7":"Le Sud-Ouest",
    "8":"L-Ile-Bizard-Sainte-Genevieve","9":"Mercier-Hochelaga-Maisonneuve",
    "10":"Montreal-Nord","11":"Outremont","12":"Pierrefonds-Roxboro",
    "13":"Riviere-des-Prairies-Pointe-aux-Trembles","14":"Rosemont-La Petite-Patrie",
    "15":"Saint-Laurent","16":"Saint-Leonard","17":"Verdun",
    "18":"Ville-Marie","19":"Villeray-Saint-Michel-Parc-Extension",
    # Villes liées / demerged municipalities (20–40+)
    "20":"Baie-D-Urfe","21":"Beaconsfield","22":"Cote-Saint-Luc",
    "23":"Dollard-Des-Ormeaux","24":"Dorval","25":"Hampstead",
    "26":"Kirkland","27":"L-Ile-Dorval","28":"Mont-Royal",
    "29":"Montreal-Est","30":"Montreal-Ouest","31":"Pointe-Claire",
    "32":"Sainte-Anne-de-Bellevue","33":"Senneville","34":"Westmount",
}

# MUNICIPALITE field codes → borough/city name
# Source: Quebec municipalite codes for Montreal agglomeration
MUNICIPALITE_MAP = {
    # Ville de Montréal arrondissements (code = 2-digit)
    "1":"Ahuntsic-Cartierville","2":"Anjou",
    "3":"Cote-des-Neiges-Notre-Dame-de-Grace","4":"Lachine","5":"LaSalle",
    "6":"Le Plateau-Mont-Royal","7":"Le Sud-Ouest",
    "8":"L-Ile-Bizard-Sainte-Genevieve","9":"Mercier-Hochelaga-Maisonneuve",
    "10":"Montreal-Nord","11":"Outremont","12":"Pierrefonds-Roxboro",
    "13":"Riviere-des-Prairies-Pointe-aux-Trembles","14":"Rosemont-La Petite-Patrie",
    "15":"Saint-Laurent","16":"Saint-Leonard","17":"Verdun",
    "18":"Ville-Marie","19":"Villeray-Saint-Michel-Parc-Extension",
    # Also with leading zeros
    "01":"Ahuntsic-Cartierville","02":"Anjou",
    "03":"Cote-des-Neiges-Notre-Dame-de-Grace","04":"Lachine","05":"LaSalle",
    "06":"Le Plateau-Mont-Royal","07":"Le Sud-Ouest",
    "08":"L-Ile-Bizard-Sainte-Genevieve","09":"Mercier-Hochelaga-Maisonneuve",
    "10":"Montreal-Nord","11":"Outremont","12":"Pierrefonds-Roxboro",
    "13":"Riviere-des-Prairies-Pointe-aux-Trembles","14":"Rosemont-La Petite-Patrie",
    "15":"Saint-Laurent","16":"Saint-Leonard","17":"Verdun",
    "18":"Ville-Marie","19":"Villeray-Saint-Michel-Parc-Extension",
    # Demerged municipalities (reconstituted cities on island)
    "48":"Westmount","46":"Mont-Royal","44":"Outremont",
    "62":"Cote-Saint-Luc","64":"Hampstead",
    "38":"Dollard-Des-Ormeaux","40":"Dorval","42":"Pointe-Claire",
    "34":"Beaconsfield","36":"Baie-D-Urfe","32":"Sainte-Anne-de-Bellevue",
    "30":"Senneville","60":"Kirkland","58":"L-Ile-Dorval",
    "56":"Montreal-Ouest","54":"Montreal-Est","50":"Montreal",
}

def borough_from_code(v):
    """Handle NO_ARROND_ILE_CUM values like 'REM19', 'REM06', '19', '6'."""
    if not v: return ""
    s = str(v).strip()
    # Strip common prefixes: REM, ILE, MTL, etc.
    s = re.sub(r'^[A-Za-z]+', '', s).lstrip("0") or "0"
    return ARROND_CODE_MAP.get(s, "")

def backfill_boroughs_from_permits():
    """Use permits CSV (which has NOM_ARROND text) to fill in missing borough names."""
    permits_path=SOURCES["permits"]["path"]
    if not permits_path.exists(): print("  Cannot backfill: permits CSV missing"); return
    print("  Backfilling borough names from permits CSV...")
    street_to_borough={}
    with open(permits_path,encoding="utf-8",errors="replace") as f:
        sample=f.readline()
    sep=";" if sample.count(";")>sample.count(",") else ","
    with open(permits_path,encoding="utf-8",errors="replace") as f:
        reader=csv.DictReader(f,delimiter=sep)
        for row in reader:
            # Actual column in Montreal permits CSV is 'arrondissement'
            borough=(row.get("arrondissement") or row.get("NOM_ARROND") or row.get("ARRONDISSEMENT") or "").strip()
            # Street is in 'emplacement' (e.g. "81 rue Montigny") or NOM_RUE
            emplacement=(row.get("emplacement") or row.get("NOM_RUE") or "").strip()
            # Extract street name from emplacement (skip leading civic number)
            m=re.match(r"^\s*\d+\s+(.+)$", emplacement)
            street=m.group(1).strip() if m else emplacement
            if borough and street:
                sn=norm(street)
                if sn: street_to_borough[sn]=borough
    if not street_to_borough: print("  No mappings found in permits"); return

    # Build a secondary index: word → set of street_norms containing that word
    # This lets us find partial matches while still requiring multiple-word confirmation
    word_to_streets = {}
    for sn, borough_name in street_to_borough.items():
        for w in sn.split():
            if len(w) >= 4:
                if w not in word_to_streets:
                    word_to_streets[w] = []
                word_to_streets[w].append(sn)

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, street_norm FROM properties WHERE borough IS NULL OR borough=''")
    rows = c.fetchall()
    updated = 0
    for pid, sn in rows:
        if not sn: continue
        # Strategy 1: exact match on full street_norm
        b = street_to_borough.get(sn)
        if not b:
            # Strategy 2: exact match after stripping street-type prefix
            TYPES = ("rue ","avenue ","boulevard ","place ","chemin ","cote ","montee ")
            sn_stripped = sn
            for t in TYPES:
                if sn_stripped.startswith(t):
                    sn_stripped = sn_stripped[len(t):]
                    break
            b = street_to_borough.get(sn_stripped)
            if not b:
                # Try with "rue " prefix added
                b = street_to_borough.get("rue " + sn_stripped)
        if b:
            c.execute("UPDATE properties SET borough=? WHERE id=?", (b, pid))
            updated += 1
    conn.commit()
    c.execute("SELECT borough,COUNT(*) FROM properties WHERE borough!=\'\' GROUP BY borough ORDER BY 2 DESC LIMIT 5")
    top=c.fetchall()
    conn.close()
    print(f"  Backfilled {updated:,} props. Top boroughs: {[r[0] for r in top]}")


# ── STM GTFS INTEGRATION ──────────────────────────────────────────────────────
# route_type codes: 0=tram, 1=metro/subway, 3=bus
METRO_ROUTE_TYPE = 1
BUS_ROUTE_TYPE   = 3

# High-frequency threshold: routes with 100+ trips/weekday
HIGH_FREQ_TRIP_THRESHOLD = 100

# In-memory stop list (loaded at startup)
STM_STOPS = []  # list of dicts: {stop_id, name, lat, lng, type, is_metro, is_high_freq}
STM_LOADED = False

# Simple grid spatial index: cell_key → [stop_indices]
_GRID = {}
_GRID_SIZE = 0.01  # degrees (~1km)

def _grid_key(lat, lng):
    return (int(lat / _GRID_SIZE), int(lng / _GRID_SIZE))

def _grid_cells_near(lat, lng, radius_deg):
    """Return grid cell keys within radius_deg of (lat, lng)."""
    steps = int(radius_deg / _GRID_SIZE) + 1
    cy, cx = int(lat / _GRID_SIZE), int(lng / _GRID_SIZE)
    return [(cy + dy, cx + dx)
            for dy in range(-steps, steps + 1)
            for dx in range(-steps, steps + 1)]

def build_stm_db():
    """Download STM GTFS, parse stops/routes/trips, write to SQLite."""
    zip_path = SOURCES["stm_gtfs"]["path"]
    if not zip_path.exists():
        download(SOURCES["stm_gtfs"]["url"], zip_path, SOURCES["stm_gtfs"]["desc"])

    print("  Parsing STM GTFS…")
    with zipfile.ZipFile(zip_path, "r") as zf:
        names = zf.namelist()
        print(f"    Files in GTFS zip: {[n for n in names if n.endswith('.txt')]}")

        # ── stops.txt → stop_id, name, lat, lng, location_type ──
        stops = {}
        with zf.open("stops.txt") as f:
            reader = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8"))
            for row in reader:
                stop_id = row.get("stop_id","").strip()
                try:
                    lat = float(row.get("stop_lat","") or 0)
                    lng = float(row.get("stop_lon","") or 0)
                except ValueError:
                    continue
                if lat == 0 or lng == 0: continue
                stops[stop_id] = {
                    "stop_id": stop_id,
                    "name": row.get("stop_name","").strip(),
                    "lat": lat, "lng": lng,
                    "route_types": set(),
                    "trip_count": 0,
                }
        print(f"    Stops: {len(stops):,}")

        # ── routes.txt → route_id → route_type ──
        route_types = {}
        with zf.open("routes.txt") as f:
            reader = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8"))
            for row in reader:
                rid = row.get("route_id","").strip()
                try: rt = int(row.get("route_type","3"))
                except: rt = 3
                route_types[rid] = rt
        print(f"    Routes: {len(route_types):,}")

        # ── trips.txt → trip_id → route_id ──
        trip_to_route = {}
        with zf.open("trips.txt") as f:
            reader = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8"))
            for row in reader:
                trip_to_route[row.get("trip_id","").strip()] = row.get("route_id","").strip()
        print(f"    Trips: {len(trip_to_route):,}")

        # ── stop_times.txt → count trips per stop, tag route types ──
        # stop_times is large (~10M rows for STM); we stream it
        stop_trip_sets = {}  # stop_id → set of trip_ids (to count unique trips)
        with zf.open("stop_times.txt") as f:
            reader = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8"))
            for i, row in enumerate(reader):
                sid  = row.get("stop_id","").strip()
                tid  = row.get("trip_id","").strip()
                if sid not in stops: continue
                rid  = trip_to_route.get(tid,"")
                rt   = route_types.get(rid, 3)
                stops[sid]["route_types"].add(rt)
                if sid not in stop_trip_sets:
                    stop_trip_sets[sid] = set()
                stop_trip_sets[sid].add(tid)
                if i % 500000 == 0 and i > 0:
                    print(f"    stop_times: {i:,} rows…", end="\r", flush=True)
        print(f"    stop_times: done ({i+1:,} rows)")

        # Assign trip counts
        for sid, trips in stop_trip_sets.items():
            if sid in stops:
                stops[sid]["trip_count"] = len(trips)

    # Write to SQLite
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.executescript("""
        DROP TABLE IF EXISTS stm_stops;
        CREATE TABLE stm_stops (
            stop_id    TEXT PRIMARY KEY,
            name       TEXT,
            lat        REAL,
            lng        REAL,
            is_metro   INTEGER DEFAULT 0,
            is_highfreq INTEGER DEFAULT 0,
            trip_count INTEGER DEFAULT 0
        );
        CREATE INDEX idx_stm_lat ON stm_stops(lat);
        CREATE INDEX idx_stm_lng ON stm_stops(lng);
    """)

    metro_count = 0
    highfreq_count = 0

    # ── Deduplicate metro stations ────────────────────────────────────────────
    # GTFS has multiple entries per physical metro station (each platform/entrance
    # is a separate stop). Collapse by station name → centroid of all platform coords.
    # This ensures "Berri-UQAM" appears once at the correct station centre.
    metro_by_name = {}   # name → {lat_sum, lng_sum, count}
    bus_stops = []       # regular bus stops kept as-is

    for stop in stops.values():
        is_metro = int(METRO_ROUTE_TYPE in stop["route_types"])
        if is_metro:
            nm = stop["name"].strip()
            # Normalise station names: strip direction suffixes "(direction Nord)" etc.
            nm = re.sub(r'\s*\([^)]+\)\s*$', '', nm).strip()
            if nm not in metro_by_name:
                metro_by_name[nm] = {"lat_sum":0,"lng_sum":0,"count":0,"trip_count":0}
            metro_by_name[nm]["lat_sum"]    += stop["lat"]
            metro_by_name[nm]["lng_sum"]    += stop["lng"]
            metro_by_name[nm]["count"]      += 1
            metro_by_name[nm]["trip_count"] += stop["trip_count"]
        else:
            is_highfreq = int(stop["trip_count"] >= HIGH_FREQ_TRIP_THRESHOLD)
            bus_stops.append((
                stop["stop_id"], stop["name"], stop["lat"], stop["lng"],
                0, is_highfreq, stop["trip_count"]
            ))
            if is_highfreq: highfreq_count += 1

    rows = list(bus_stops)

    # Add one deduplicated entry per metro station
    for i, (nm, agg) in enumerate(metro_by_name.items()):
        lat = agg["lat_sum"] / agg["count"]
        lng = agg["lng_sum"] / agg["count"]
        rows.append((f"metro_{i}", nm, lat, lng, 1, 1, agg["trip_count"]))
        metro_count += 1

    c.executemany("INSERT OR REPLACE INTO stm_stops VALUES(?,?,?,?,?,?,?)", rows)
    conn.commit()
    conn.close()
    print(f"  ✓ STM: {len(stops):,} raw stops → {metro_count} metro stations (deduped) · {highfreq_count} high-freq bus")

def load_stm_stops():
    """Load STM stops from SQLite into memory and build spatial grid index."""
    global STM_STOPS, _GRID, STM_LOADED
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT * FROM stm_stops")
        rows = c.fetchall()
        conn.close()
    except Exception as e:
        print(f"  STM stops not loaded: {e}")
        return

    STM_STOPS = [dict(r) for r in rows]
    _GRID = {}
    for i, stop in enumerate(STM_STOPS):
        key = _grid_key(stop["lat"], stop["lng"])
        if key not in _GRID: _GRID[key] = []
        _GRID[key].append(i)
    STM_LOADED = True
    metro  = sum(1 for s in STM_STOPS if s["is_metro"])
    hfreq  = sum(1 for s in STM_STOPS if s["is_highfreq"] and not s["is_metro"])
    print(f"  ✓ STM loaded: {len(STM_STOPS):,} stops ({metro} metro, {hfreq} high-freq bus)")

def nearest_stm(lat, lng):
    """
    Return nearest metro station and nearest high-frequency bus stop.
    Uses grid index for O(1) average lookup.
    Returns: (metro_name, metro_dist_m, bus_name, bus_dist_m)
    """
    if not STM_LOADED or not lat or not lng:
        return None, None, None, None

    best_metro = (None, float("inf"))
    best_bus   = (None, float("inf"))

    # Search expanding rings of grid cells until we have candidates in both categories
    for radius_deg in [0.005, 0.015, 0.04, 0.15]:
        cells = _grid_cells_near(lat, lng, radius_deg)
        seen = set()
        for cell in cells:
            for idx in _GRID.get(cell, []):
                if idx in seen: continue
                seen.add(idx)
                stop = STM_STOPS[idx]
                d = haversine_m(lat, lng, stop["lat"], stop["lng"])
                if stop["is_metro"] and d < best_metro[1]:
                    best_metro = (stop["name"], d)
                elif stop["is_highfreq"] and not stop["is_metro"] and d < best_bus[1]:
                    best_bus = (stop["name"], d)
        # Stop expanding once we have plausible candidates
        if best_metro[0] and best_metro[1] < 5000 and best_bus[0] and best_bus[1] < 1000:
            break

    return (
        best_metro[0], round(best_metro[1]) if best_metro[1] < float("inf") else None,
        best_bus[0],   round(best_bus[1])   if best_bus[1]   < float("inf") else None,
    )


# ── AMENITY DATA (parks, facilities, points of interest, commercial) ──────────

# In-memory spatial stores
PARKS_STORE      = []  # {name, lat, lng, area_m2, type}
FACILITIES_STORE = []  # {name, lat, lng, types, installations, borough}
POI_STORE        = []  # {name, lat, lng, famille, categorie}
COMMERCIAL_STORE = []  # {name, lat, lng, usage, vacant}

# Shared grid index per store
_PARK_GRID    = {}
_FAC_GRID     = {}
_POI_GRID     = {}
_COM_GRID     = {}
AMENITIES_LOADED = False

def _build_grid(items, lat_key="lat", lng_key="lng"):
    grid = {}
    for i, item in enumerate(items):
        lat, lng = item.get(lat_key), item.get(lng_key)
        if lat and lng:
            key = _grid_key(lat, lng)
            if key not in grid: grid[key] = []
            grid[key].append(i)
    return grid

def _nearest_in_store(store, grid, lat, lng, max_m=1000, filter_fn=None):
    """Find nearest item in store within max_m metres."""
    if not store or not lat or not lng: return None, None
    best_item, best_d = None, float("inf")
    radius_deg = max_m / 111000 + _GRID_SIZE
    for cell in _grid_cells_near(lat, lng, radius_deg):
        for idx in grid.get(cell, []):
            item = store[idx]
            if filter_fn and not filter_fn(item): continue
            d = haversine_m(lat, lng, item["lat"], item["lng"])
            if d <= max_m and d < best_d:
                best_d, best_item = d, item
    return best_item, round(best_d) if best_d < float("inf") else None

def _count_within(store, grid, lat, lng, radius_m, filter_fn=None):
    """Count items in store within radius_m metres."""
    if not store or not lat or not lng: return 0
    count = 0
    radius_deg = radius_m / 111000 + _GRID_SIZE
    seen = set()
    for cell in _grid_cells_near(lat, lng, radius_deg):
        for idx in grid.get(cell, []):
            if idx in seen: continue
            seen.add(idx)
            item = store[idx]
            if filter_fn and not filter_fn(item): continue
            if haversine_m(lat, lng, item["lat"], item["lng"]) <= radius_m:
                count += 1
    return count

# ── PARKS ──────────────────────────────────────────────────────────────────────
def build_parks_db():
    """
    Build parks database from multiple sources in priority order:
    1. Overpass API (OpenStreetMap) — always available, has centroids
    2. Montreal CKAN GeoJSON — if Overpass fails
    """
    print("  Fetching parks from Overpass API (OpenStreetMap)…")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.executescript("""
        DROP TABLE IF EXISTS parks;
        CREATE TABLE parks(id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT, lat REAL, lng REAL, area_m2 REAL, ptype TEXT);
        CREATE INDEX idx_pk_lat ON parks(lat);
        CREATE INDEX idx_pk_lng ON parks(lng);
    """)

    batch = []

    # Overpass query: all parks and green spaces in Montreal bounding box
    # bbox: south,west,north,east
    overpass_query = """
[out:json][timeout:60];
(
  node["leisure"="park"](45.40,-74.02,45.71,-73.47);
  way["leisure"="park"](45.40,-74.02,45.71,-73.47);
  relation["leisure"="park"](45.40,-74.02,45.71,-73.47);
  way["landuse"="grass"](45.40,-74.02,45.71,-73.47);
  way["landuse"="park"](45.40,-74.02,45.71,-73.47);
  node["leisure"="garden"](45.40,-74.02,45.71,-73.47);
  way["leisure"="garden"](45.40,-74.02,45.71,-73.47);
);
out center;
"""

    overpass_urls = [
        "https://overpass-api.de/api/interpreter",
        "https://overpass.kumi.systems/api/interpreter",
        "https://overpass.openstreetmap.ru/api/interpreter",
    ]

    success = False
    for base_url in overpass_urls:
        try:
            import urllib.parse
            data = urllib.parse.urlencode({"data": overpass_query}).encode()
            req = urllib.request.Request(base_url, data=data,
                headers={"User-Agent": "MTLPropIntel/2.0",
                         "Content-Type": "application/x-www-form-urlencoded"})
            with urllib.request.urlopen(req, timeout=90) as r:
                result = json.loads(r.read())
            elements = result.get("elements", [])
            print(f"  Overpass returned {len(elements)} elements from {base_url[:40]}")
            for el in elements:
                try:
                    tags = el.get("tags", {})
                    name = (tags.get("name:fr") or tags.get("name") or "Parc").strip()
                    ptype = tags.get("leisure") or tags.get("landuse") or "park"
                    # Nodes have lat/lon directly; ways/relations have 'center'
                    if el["type"] == "node":
                        lat, lng = el.get("lat"), el.get("lon")
                    else:
                        ctr = el.get("center", {})
                        lat, lng = ctr.get("lat"), ctr.get("lon")
                    if not lat or not lng: continue
                    if not (45.3 < lat < 45.8 and -74.1 < lng < -73.3): continue
                    area = safe_float(tags.get("area"))
                    batch.append((name, lat, lng, area, ptype))
                except Exception:
                    pass
            success = True
            break
        except Exception as e:
            print(f"  Overpass {base_url[:40]} failed: {e}")

    if not success or len(batch) < 100:
        print(f"  Overpass got {len(batch)} parks — trying Montreal CKAN fallback…")
        _build_parks_from_geojson_api_v2(c)
    
    if batch:
        c.executemany("INSERT INTO parks(name,lat,lng,area_m2,ptype) VALUES(?,?,?,?,?)", batch)
        conn.commit()
    conn.close()
    print(f"  ✓ Parks: {len(batch):,}")



def _build_parks_from_geojson_api_v2(c):
    """Try every known Montreal parks URL pattern."""
    urls = [
        # CKAN datastore search (tabular) — different base domains
        "https://donnees.montreal.ca/api/3/action/datastore_search?resource_id=35796624-15df-4503-a569-797665f8768e&limit=5000",
        "https://data.montreal.ca/api/3/action/datastore_search?resource_id=35796624-15df-4503-a569-797665f8768e&limit=5000",
        "https://donnees.montreal.ca/api/3/action/datastore_search?resource_id=f34c3555-c285-4ef3-a55c-f0f5c440ad2d&limit=5000",
        # Direct GeoJSON downloads
        "https://donnees.montreal.ca/dataset/2e9e4d2f-173a-4c3d-a5e3-565d79baa27d/resource/35796624-15df-4503-a569-797665f8768e/download/espace_vert.geojson",
        "https://data.montreal.ca/dataset/2e9e4d2f-173a-4c3d-a5e3-565d79baa27d/resource/35796624-15df-4503-a569-797665f8768e/download/espace_vert.geojson",
        "https://donnees.montreal.ca/dataset/2e9e4d2f-173a-4c3d-a5e3-565d79baa27d/resource/f34c3555-c285-4ef3-a55c-f0f5c440ad2d/download/espace_vert.geojson",
    ]

    def extract_centroid(geom):
        if not geom: return None, None
        try:
            if isinstance(geom, str): geom = json.loads(geom)
            coords = []
            def collect(obj):
                if isinstance(obj, list):
                    if obj and isinstance(obj[0], (int, float)): coords.append(obj[:2])
                    else: [collect(x) for x in obj]
            collect(geom.get("coordinates", []))
            if not coords: return None, None
            step = max(1, len(coords)//30)
            s = coords[::step]
            return sum(p[1] for p in s)/len(s), sum(p[0] for p in s)/len(s)
        except Exception: return None, None

    for url in urls:
        try:
            req = urllib.request.Request(url, headers={"User-Agent":"MTLPropIntel/2.0"})
            with urllib.request.urlopen(req, timeout=45) as r:
                raw = json.loads(r.read())
            features = (raw.get("features") or
                        raw.get("result",{}).get("records") or [])
            added = 0
            for feat in features:
                try:
                    props = feat.get("properties", feat)
                    name = (props.get("Nom") or props.get("NOM") or "").strip() or "Parc (sans nom)"
                    area = safe_float(props.get("SUPERFICIE"))
                    lat = safe_float(props.get("LATITUDE") or props.get("Y_CENTROID"))
                    lng = safe_float(props.get("LONGITUDE") or props.get("X_CENTROID"))
                    if not lat or not lng:
                        lat, lng = extract_centroid(feat.get("geometry") or props.get("geometry"))
                    if not lat or not lng: continue
                    if not (45.3<lat<45.8 and -74.1<lng<-73.3): continue
                    c.execute("INSERT INTO parks(name,lat,lng,area_m2,ptype) VALUES(?,?,?,?,?)",
                              (name, lat, lng, area, ptype))
                    added += 1
                except Exception: pass
            if added > 0:
                print(f"  CKAN fallback: {added} parks from {url[:60]}")
                return
        except Exception as e:
            print(f"  Failed: {url[:60]} — {e}")

def _build_parks_from_geojson_api():
    """
    Download espace_vert.json (GeoJSON FeatureCollection) and compute
    polygon centroids by averaging vertex coordinates.
    URL confirmed via resource_show API: espace_vert.json (not .geojson).
    """
    PARKS_JSON_URL = ("https://donnees.montreal.ca/dataset/2e9e4d2f-173a-4c3d-a5e3-565d79baa27d"
                      "/resource/35796624-15df-4503-a569-797665f8768e/download/espace_vert.json")
    parks_json_path = DATA_DIR / "espace_vert.json"

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.executescript("""
        DROP TABLE IF EXISTS parks;
        CREATE TABLE parks(id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT, lat REAL, lng REAL, area_m2 REAL, ptype TEXT);
        CREATE INDEX idx_pk_lat ON parks(lat);
        CREATE INDEX idx_pk_lng ON parks(lng);
    """)

    # Download if needed
    if not parks_json_path.exists():
        try:
            print("  Downloading espace_vert.json (~28MB)…")
            download(PARKS_JSON_URL, parks_json_path, "Parks GeoJSON")
        except Exception as e:
            print(f"  Parks download failed: {e}")
            conn.close()
            return

    if not parks_json_path.exists():
        print("  Parks file not found after download attempt")
        conn.close()
        return

    print("  Parsing parks GeoJSON…")

    def centroid(coords):
        """Average all vertices in a polygon (or multipolygon) coordinate structure."""
        pts = []
        def collect(obj):
            if not obj: return
            if isinstance(obj[0], (int, float)):
                pts.append(obj[:2])
            else:
                for item in obj: collect(item)
        collect(coords)
        if not pts: return None, None
        step = max(1, len(pts) // 100)   # sample for speed
        sample = pts[::step]
        lng = sum(p[0] for p in sample) / len(sample)
        lat = sum(p[1] for p in sample) / len(sample)
        return (lat, lng) if (45.3 < lat < 45.8 and -74.1 < lng < -73.3) else (None, None)

    try:
        with open(parks_json_path, encoding="utf-8", errors="replace") as f:
            gj = json.load(f)
    except Exception as e:
        print(f"  Parks JSON parse error: {e}")
        conn.close()
        return

    batch = []
    skipped = 0
    for feat in gj.get("features", []):
        try:
            props = feat.get("properties") or {}
            name  = (props.get("Nom") or props.get("NOM") or props.get("TOPONYME") or "").strip() or "Parc (sans nom)"
            area  = safe_float(props.get("SUPERFICIE"))
            geom  = feat.get("geometry") or {}
            lat, lng = centroid(geom.get("coordinates", []))
            if lat is None:
                skipped += 1
                continue
            batch.append((name, lat, lng, area, ptype))
        except Exception:
            skipped += 1

    if batch:
        c.executemany("INSERT INTO parks(name,lat,lng,area_m2,ptype) VALUES(?,?,?,?,?)", batch)
        conn.commit()
    conn.close()
    print(f"  ✓ Parks: {len(batch):,} ({skipped} skipped)")

def load_parks():
    global PARKS_STORE, _PARK_GRID
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT * FROM parks")
        PARKS_STORE = [dict(r) for r in c.fetchall()]
        conn.close()
        _PARK_GRID = _build_grid(PARKS_STORE)
        print(f"  ✓ Parks loaded: {len(PARKS_STORE):,}")
    except Exception as e:
        print(f"  Parks not loaded: {e}")

# ── COMMERCIAL PREMISES ────────────────────────────────────────────────────────
def build_commercial_db():
    csv_path = SOURCES["commercial"]["path"]
    if not csv_path.exists():
        download(SOURCES["commercial"]["url"], csv_path, SOURCES["commercial"]["desc"])

    print("  Parsing commercial premises CSV…")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.executescript("""
        DROP TABLE IF EXISTS commercial;
        CREATE TABLE commercial (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            name    TEXT,
            lat     REAL,
            lng     REAL,
            usage1  TEXT,
            usage2  TEXT,
            vacant  INTEGER DEFAULT 0,
            arrond  TEXT
        );
        CREATE INDEX idx_cm_lat ON commercial(lat);
    """)

    with open(csv_path, encoding="utf-8", errors="replace") as f:
        sample = f.readline()
    sep = ";" if sample.count(";") > sample.count(",") else ","

    count = 0
    batch = []
    with open(csv_path, encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f, delimiter=sep)
        for row in reader:
            try:
                lat = safe_float(row.get("LAT") or row.get("LATITUDE") or row.get("Latitude"))
                lng = safe_float(row.get("LONG") or row.get("LONGITUDE") or row.get("Longitude"))
                if not lat or not lng: continue
                vacant_str = (row.get("NOM_ETAB") or "").upper()
                is_vacant = 1 if "VACANT" in vacant_str else 0
                batch.append((
                    (row.get("NOM_ETAB") or "").strip(),
                    lat, lng,
                    (row.get("USAGE1") or "").strip(),
                    (row.get("USAGE2") or "").strip(),
                    is_vacant,
                    (row.get("ARRONDISSEMENT") or "").strip(),
                ))
                count += 1
            except Exception: pass

    if batch:
        c.executemany("INSERT INTO commercial(name,lat,lng,usage1,usage2,vacant,arrond) VALUES(?,?,?,?,?,?,?)", batch)
        conn.commit()
    conn.close()
    print(f"  ✓ Commercial premises: {count:,}")

def load_commercial():
    global COMMERCIAL_STORE, _COM_GRID
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT * FROM commercial")
        COMMERCIAL_STORE = [dict(r) for r in c.fetchall()]
        conn.close()
        _COM_GRID = _build_grid(COMMERCIAL_STORE)
        print(f"  ✓ Commercial: {len(COMMERCIAL_STORE):,}")
    except Exception as e:
        print(f"  Commercial not loaded: {e}")

# ── FACILITIES & POI (via CKAN live API) ───────────────────────────────────────
def fetch_ckan_geojson(resource_id, limit=5000):
    """Fetch all records from a CKAN GeoJSON resource."""
    url = f"{CKAN_BASE}/datastore_search?resource_id={resource_id}&limit={limit}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "MTLPropIntel/2.0"})
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read())
        return data.get("result", {}).get("records", [])
    except Exception as e:
        print(f"  CKAN fetch failed ({resource_id}): {e}")
        return []


def discover_facilities_resource_id():
    """Find the current CKAN resource ID for facilities by trying known package slugs."""
    global CKAN_FACILITIES_ID
    for slug in CKAN_FACILITIES_PKGS:
        try:
            url = f"https://donnees.montreal.ca/api/3/action/package_show?id={slug}"
            req = urllib.request.Request(url, headers={"User-Agent":"MTLPropIntel/2.0"})
            with urllib.request.urlopen(req, timeout=15) as r:
                pkg = json.loads(r.read())
            if not pkg.get("success"): continue
            resources = pkg["result"].get("resources", [])
            # Prefer CSV French, then GeoJSON, then anything with datastore
            preferred = (
                [r for r in resources if r.get("format","").upper()=="CSV" and "français" in r.get("name","").lower()] or
                [r for r in resources if r.get("format","").upper()=="GEOJSON"] or
                [r for r in resources if r.get("datastore_active")] or
                [r for r in resources if r.get("format","").upper() in ("CSV","JSON")]
            )
            if preferred:
                CKAN_FACILITIES_ID = preferred[0]["id"]
                print(f"  ✓ Facilities resource: {CKAN_FACILITIES_ID} ({slug})")
                return CKAN_FACILITIES_ID
        except Exception:
            pass
    print("  ⚠ Facilities: no resource found in known packages")
    return None

def load_facilities_from_ckan():
    """Load lieux-batiments-vocation-publique from CKAN into memory."""
    global FACILITIES_STORE, _FAC_GRID
    path = DATA_DIR / "facilities_cache.json"

    # Use cache if fresh (< 7 days) and non-empty
    if path.exists() and (path.stat().st_mtime > __import__("time").time() - 86400 * 7):
        try:
            with open(path) as f:
                FACILITIES_STORE = json.load(f)
            if len(FACILITIES_STORE) == 0:
                print("  Facilities cache empty — re-fetching…")
                path.unlink(missing_ok=True)
            else:
                _FAC_GRID = _build_grid(FACILITIES_STORE)
                print(f"  ✓ Facilities (cache): {len(FACILITIES_STORE):,}")
                return
        except Exception: pass

    # Discover resource ID if not yet found
    rid = CKAN_FACILITIES_ID or discover_facilities_resource_id()
    print(f"  Fetching public facilities from CKAN (resource: {rid})…")
    records = []
    if rid:
        records = fetch_ckan_geojson(rid, limit=10000)
    if not records:
        # Try confirmed-working IDs (from package_show on 2026-05-03)
        for rid_try in [
            "4731b64f-29cc-4e08-bc44-8752ae2fcafb",  # CSV French (confirmed)
            "2b8bf94c-6b9a-4d60-8091-5b82467a4138",  # GeoJSON French
            "81080d62-5c89-41e6-a401-99f77c459594",  # CSV English
        ]:
            records = fetch_ckan_geojson(rid_try, limit=10000)
            if records:
                print(f"  ✓ Facilities resource {rid_try} returned {len(records)} records")
                break
    if not records:
        try:
            print("  Facilities resource 404 — discovering current ID via CKAN…")
            # discover_facilities_resource_id() already tried all slugs above
            pass
        except Exception as e:
            print(f"  Facilities discovery failed: {e}")
    store = []
    for rec in records:
        try:
            # Try all known lat/lng column name variants
            # Confirmed column names from API 2026-05-03: lat, long
            lat = safe_float(rec.get("lat") or rec.get("latitude") or rec.get("Latitude") or rec.get("LAT"))
            lng = safe_float(rec.get("long") or rec.get("longitude") or rec.get("Longitude") or rec.get("LON"))
            if not lat or not lng: continue
            if not (45.3 < lat < 45.8 and -74.1 < lng < -73.3): continue
            # Column names confirmed: titre_lieu, types, arrondissements
            name     = (rec.get("titre_lieu") or rec.get("nom") or rec.get("name") or "").strip()
            fac_type = (rec.get("types") or rec.get("categories") or rec.get("type") or "").strip()
            borough  = (rec.get("arrondissements") or rec.get("arrondissement") or "").strip()
            installs = (rec.get("installations") or rec.get("activites") or "").strip()
            store.append({
                "name":          name,
                "lat":           lat, "lng": lng,
                "types":         fac_type,
                "borough":       borough,
                "installations": installs,
            })
        except Exception: pass

    FACILITIES_STORE = store
    _FAC_GRID = _build_grid(FACILITIES_STORE)
    try:
        with open(path, "w") as f: json.dump(store, f)
    except Exception: pass
    print(f"  ✓ Facilities: {len(FACILITIES_STORE):,}")

def load_poi_from_ckan():
    """Load lieux d'intérêt (POI) from CKAN into memory."""
    global POI_STORE, _POI_GRID
    path = DATA_DIR / "poi_cache.json"

    if path.exists() and (path.stat().st_mtime > __import__("time").time() - 86400 * 7):
        try:
            with open(path) as f:
                POI_STORE = json.load(f)
            _POI_GRID = _build_grid(POI_STORE)
            print(f"  ✓ POI (cache): {len(POI_STORE):,}")
            return
        except Exception: pass

    print("  Fetching points of interest from CKAN…")
    records = fetch_ckan_geojson(CKAN_POI_ID, limit=5000)
    store = []
    for rec in records:
        try:
            lat = safe_float(rec.get("Latitude") or rec.get("latitude"))
            lng = safe_float(rec.get("Longitude") or rec.get("longitude"))
            if not lat or not lng: continue
            store.append({
                "name":      (rec.get("Nom français") or rec.get("name") or "").strip(),
                "lat":       lat, "lng": lng,
                "famille":   (rec.get("Famille") or "").strip(),
                "categorie": (rec.get("Catégorie") or "").strip(),
            })
        except Exception: pass

    POI_STORE = store
    _POI_GRID = _build_grid(POI_STORE)
    try:
        with open(path, "w") as f: json.dump(store, f)
    except Exception: pass
    print(f"  ✓ POI: {len(POI_STORE):,}")

# ── ADDRESS GEOCODER ───────────────────────────────────────────────────────────
# Cache: street_norm → [(civic_num, lat, lng)]
ADDR_GEOCACHE = {}
GEOCACHE_LOADED = False

def build_geocache():
    """
    Build address geocache from the adresses-ponctuelles GeoJSON.
    Resource ID d3f65ec7 is a GeoJSON FeatureCollection with Point geometry
    (lng, lat) and properties: TEXTE (full address), ADDR_DE (civic from).
    URL is signed and expires — fetched fresh via resource_show each build.
    Saves to geocache.json for reuse across restarts.
    """
    global ADDR_GEOCACHE, GEOCACHE_LOADED
    cache_path = DATA_DIR / "geocache.json"
    ADDR_RID   = "d3f65ec7-57d0-44bc-858c-93e449dbdcbc"

    # Load from cache if fresh and complete
    if cache_path.exists() and (cache_path.stat().st_mtime > __import__("time").time() - 86400 * 30):
        try:
            with open(cache_path) as f:
                ADDR_GEOCACHE = json.load(f)
            total = sum(len(v) for v in ADDR_GEOCACHE.values())
            if len(ADDR_GEOCACHE) < 80000:
                print(f"  Geocache: {len(ADDR_GEOCACHE):,} streets — too few, rebuilding…")
                ADDR_GEOCACHE = {}
                cache_path.unlink(missing_ok=True)
            else:
                GEOCACHE_LOADED = True
                print(f"  ✓ Geocache (cache): {len(ADDR_GEOCACHE):,} streets, {total:,} addresses")
                return
        except Exception:
            ADDR_GEOCACHE = {}
            cache_path.unlink(missing_ok=True)

    # Get fresh signed download URL via resource_show
    geojson_path = DATA_DIR / "adresses.geojson"
    if not geojson_path.exists():
        try:
            print(f"  Getting fresh download URL for adresses.geojson…")
            rs_url = f"https://donnees.montreal.ca/api/3/action/resource_show?id={ADDR_RID}"
            req = urllib.request.Request(rs_url, headers={"User-Agent":"MTLPropIntel/2.0"})
            with urllib.request.urlopen(req, timeout=15) as r:
                rs = json.loads(r.read())
            dl_url = rs.get("result", {}).get("url", "")
            if not dl_url:
                print("  Could not get download URL from resource_show")
                return
            print(f"  Downloading adresses.geojson (~134MB)…")
            req2 = urllib.request.Request(dl_url, headers={"User-Agent":"MTLPropIntel/2.0"})
            with urllib.request.urlopen(req2, timeout=300) as r2,                  open(geojson_path, "wb") as fout:
                while True:
                    chunk = r2.read(1024 * 1024)  # 1MB chunks
                    if not chunk: break
                    fout.write(chunk)
            print(f"  Downloaded: {geojson_path.stat().st_size // 1024 // 1024}MB")
        except Exception as e:
            print(f"  GeoJSON download failed: {e}")
            # Fall back to paginated CKAN datastore
            _build_geocache_from_datastore(cache_path)
            return

    # Parse the GeoJSON — streaming to avoid loading 134MB into RAM at once
    print("  Parsing adresses.geojson…")
    geocache = {}
    total = 0
    skipped = 0

    try:
        with open(geojson_path, encoding="utf-8", errors="replace") as f:
            # Stream parse: read character by character to find features
            # The file is {"type":"FeatureCollection","features":[{...},{...},...]}
            # Use ijson if available, otherwise load fully (134MB is manageable)
            try:
                import ijson
                parser = ijson.items(f, "features.item")
                for feat in parser:
                    try:
                        geom = feat.get("geometry") or {}
                        coords = geom.get("coordinates", [])
                        if not coords or len(coords) < 2: continue
                        lng, lat = float(coords[0]), float(coords[1])
                        if not (45.3 < lat < 45.8 and -74.1 < lng < -73.3):
                            skipped += 1; continue
                        props = feat.get("properties") or {}
                        # TEXTE = "#4597" (civic only), GENERIQUE = "rue", SPECIFIQUE = "Franchère"
                        # Full street = "{GENERIQUE} {SPECIFIQUE}"
                        civic_from = safe_int(props.get("ADDR_DE") or props.get("addr_de"))
                        generique  = (props.get("GENERIQUE") or props.get("generique") or "").strip()
                        specifique = (props.get("SPECIFIQUE") or props.get("specifique") or "").strip()
                        if generique and specifique:
                            street_name = f"{generique} {specifique}"
                        else:
                            # Fallback: try parsing from TEXTE
                            texte = (props.get("TEXTE") or "").strip()
                            m = re.match(r"#?(\d+[a-zA-Z]?)\s+(.+)", texte)
                            if m:
                                civic_from = civic_from or safe_int(m.group(1))
                                street_name = m.group(2).strip()
                            else:
                                street_name = texte
                        if not street_name: continue
                        sn = norm(street_name)
                        if not sn: continue
                        entry = [civic_from or 0, round(lat, 6), round(lng, 6)]
                        if sn not in geocache: geocache[sn] = []
                        geocache[sn].append(entry)
                        for pfx in ("rue ","avenue ","boulevard ","place ","chemin "):
                            if sn.startswith(pfx):
                                bare = sn[len(pfx):]
                                if bare:
                                    if bare not in geocache: geocache[bare] = []
                                    geocache[bare].append(entry)
                                break
                        total += 1
                        if total % 50000 == 0:
                            print(f"\r  Geocache: {total:,} addresses…", end="", flush=True)
                    except Exception:
                        pass
            except ImportError:
                # No ijson — load fully into RAM (134MB is fine)
                f.seek(0)
                gj = json.load(f)
                for feat in gj.get("features", []):
                    try:
                        geom = feat.get("geometry") or {}
                        coords = geom.get("coordinates", [])
                        if not coords or len(coords) < 2: continue
                        lng, lat = float(coords[0]), float(coords[1])
                        if not (45.3 < lat < 45.8 and -74.1 < lng < -73.3):
                            skipped += 1; continue
                        props = feat.get("properties") or {}
                        # TEXTE = "#4597" (civic only), GENERIQUE = "rue", SPECIFIQUE = "Franchère"
                        # Full street = "{GENERIQUE} {SPECIFIQUE}"
                        civic_from = safe_int(props.get("ADDR_DE") or props.get("addr_de"))
                        generique  = (props.get("GENERIQUE") or props.get("generique") or "").strip()
                        specifique = (props.get("SPECIFIQUE") or props.get("specifique") or "").strip()
                        if generique and specifique:
                            street_name = f"{generique} {specifique}"
                        else:
                            # Fallback: try parsing from TEXTE
                            texte = (props.get("TEXTE") or "").strip()
                            m = re.match(r"#?(\d+[a-zA-Z]?)\s+(.+)", texte)
                            if m:
                                civic_from = civic_from or safe_int(m.group(1))
                                street_name = m.group(2).strip()
                            else:
                                street_name = texte
                        if not street_name: continue
                        sn = norm(street_name)
                        if not sn: continue
                        entry = [civic_from or 0, round(lat, 6), round(lng, 6)]
                        if sn not in geocache: geocache[sn] = []
                        geocache[sn].append(entry)
                        for pfx in ("rue ","avenue ","boulevard ","place ","chemin "):
                            if sn.startswith(pfx):
                                bare = sn[len(pfx):]
                                if bare:
                                    if bare not in geocache: geocache[bare] = []
                                    geocache[bare].append(entry)
                                break
                        total += 1
                        if total % 50000 == 0:
                            print(f"\r  Geocache: {total:,} addresses…", end="", flush=True)
                    except Exception:
                        pass
    except Exception as e:
        print(f"\n  GeoJSON parse error: {e}")
        if total < 1000:
            print("  Falling back to CKAN datastore…")
            _build_geocache_from_datastore(cache_path)
            return

    print(f"\n  ✓ Geocache: {len(geocache):,} street keys, {total:,} addresses ({skipped:,} skipped)")
    ADDR_GEOCACHE = geocache
    GEOCACHE_LOADED = True
    try:
        with open(cache_path, "w") as f:
            json.dump(geocache, f, separators=(",",":"))
        print(f"  Geocache saved ({cache_path.stat().st_size // 1024 // 1024}MB)")
    except Exception as e:
        print(f"  Geocache save failed: {e}")


def _build_geocache_from_datastore(cache_path):
    """Fallback: build geocache from CKAN datastore API (paginated, slower)."""
    global ADDR_GEOCACHE, GEOCACHE_LOADED
    ADDR_RID = "fed5fd02-5535-458e-b13f-66e7a31a6d78"
    print("  Building geocache from CKAN datastore (paginated fallback)…")
    geocache = {}
    total = 0
    offset = 0
    while True:
        try:
            url = (f"https://donnees.montreal.ca/api/3/action/datastore_search"
                   f"?resource_id={ADDR_RID}&limit=10000&offset={offset}")
            req = urllib.request.Request(url, headers={"User-Agent":"MTLPropIntel/2.0"})
            with urllib.request.urlopen(req, timeout=60) as r:
                data = json.loads(r.read())
            records = data.get("result", {}).get("records", [])
            if not records: break
            for rec in records:
                try:
                    lat = safe_float(rec.get("LATITUDE") or rec.get("Latitude"))
                    lng = safe_float(rec.get("LONGITUDE") or rec.get("Longitude"))
                    if not lat or not lng: continue
                    if not (45.3 < lat < 45.8 and -74.1 < lng < -73.3): continue
                    civic_from  = safe_int(rec.get("ADDR_DE"))
                    generique   = (rec.get("GENERIQUE") or "").strip()
                    specifique  = (rec.get("SPECIFIQUE") or "").strip()
                    if generique and specifique:
                        street_name = f"{generique} {specifique}"
                    else:
                        texte = (rec.get("TEXTE") or "").strip()
                        m = re.match(r"#?(\d+[a-zA-Z]?)\s+(.+)", texte)
                        street_name = m.group(2).strip() if m else texte
                        if m: civic_from = civic_from or safe_int(m.group(1))
                    sn = norm(street_name)
                    if not sn: continue
                    entry = [civic_from or 0, round(lat,6), round(lng,6)]
                    if sn not in geocache: geocache[sn] = []
                    geocache[sn].append(entry)
                    for pfx in ("rue ","avenue ","boulevard ","place ","chemin "):
                        if sn.startswith(pfx):
                            bare = sn[len(pfx):]
                            if bare:
                                if bare not in geocache: geocache[bare] = []
                                geocache[bare].append(entry)
                            break
                    total += 1
                except Exception: pass
            offset += 10000
            if total % 50000 < 10000:
                print(f"\r  Geocache: {total:,}…", end="", flush=True)
            if len(records) < 10000: break
        except Exception as e:
            print(f"\n  Datastore error: {e}"); break
    print(f"\n  ✓ Geocache (datastore): {len(geocache):,} streets, {total:,} addresses")
    ADDR_GEOCACHE = geocache
    GEOCACHE_LOADED = True
    try:
        with open(cache_path,"w") as f: json.dump(geocache, f, separators=(",",":"))
    except Exception: pass
    ADDR_GEOCACHE = geocache
    GEOCACHE_LOADED = True
    try:
        with open(cache_path, "w") as f: json.dump(geocache, f, separators=(",",":"))
        print(f"  Geocache saved to {cache_path}")
    except Exception as e:
        print(f"  Geocache save failed: {e}")

def geocode_address(civic_num, street_raw):
    """
    Look up lat/lng for a civic + street using the address geocache.
    Tries multiple normalization strategies.
    Returns (lat, lng) or (None, None).
    """
    if not GEOCACHE_LOADED or not street_raw: return None, None

    def _lookup(sn):
        entries = ADDR_GEOCACHE.get(sn, [])
        if not entries: return None, None
        if civic_num:
            best = min(entries, key=lambda e: abs(e[0] - civic_num))
            if abs(best[0] - civic_num) <= 20:
                return best[1], best[2]
        return entries[0][1], entries[0][2]

    # Strategy 1: normalized street name as-is
    sn = norm(street_raw)
    result = _lookup(sn)
    if result[0]: return result

    # Strategy 2: strip parenthetical qualifier e.g. "(MTL+WMT)"
    sn2 = re.sub(r'\s*\([^)]*\)', '', sn).strip()
    if sn2 != sn:
        result = _lookup(sn2)
        if result[0]: return result

    # Strategy 3: strip common street type prefix
    TYPES = ("rue ","avenue ","boulevard ","place ","chemin ","cote ","montee ")
    for t in TYPES:
        if sn2.startswith(t):
            bare = sn2[len(t):]
            result = _lookup(bare)
            if result[0]: return result
            # Try with other type prefixes
            for t2 in TYPES:
                result = _lookup(t2 + bare)
                if result[0]: return result
            break

    # Strategy 4: partial key match on most distinctive word
    words = [w for w in sn2.split() if len(w) >= 5
             and w not in {"saint","sainte","avenue","boulevard","chemin","route","place"}]
    if words:
        best_word = max(words, key=len)
        for k, entries in ADDR_GEOCACHE.items():
            if best_word in k and entries:
                if civic_num:
                    nearby = min(entries, key=lambda e: abs(e[0]-civic_num))
                    if abs(nearby[0]-civic_num) <= 50:
                        return nearby[1], nearby[2]
                else:
                    return entries[0][1], entries[0][2]

    return None, None

# ── FULL AMENITY PROXIMITY FOR A PROPERTY ─────────────────────────────────────
def get_amenity_proximity(lat, lng):
    """
    Given a property lat/lng, return a comprehensive dict of
    nearby amenities, distances, and counts.
    """
    if not lat or not lng:
        return {}

    result = {}

    # Parks
    if PARKS_STORE:
        near_park, park_dist = _nearest_in_store(PARKS_STORE, _PARK_GRID, lat, lng, 1000)
        result["nearest_park"]      = near_park["name"] if near_park else None
        result["nearest_park_dist"] = park_dist
        result["parks_500m"]        = _count_within(PARKS_STORE, _PARK_GRID, lat, lng, 500)
        result["parks_1km"]         = _count_within(PARKS_STORE, _PARK_GRID, lat, lng, 1000)

    # Public facilities — by type
    if FACILITIES_STORE:
        def is_library(f): return "biblioth" in (f.get("installations","") + f.get("types","")).lower()
        def is_pool(f): return "piscine" in (f.get("installations","") + f.get("types","")).lower()
        def is_arena(f): return "ar" in (f.get("installations","") + f.get("types","")).lower() and "na" in (f.get("installations","") + f.get("types","")).lower()
        def is_community(f): return "communaut" in (f.get("types","") + f.get("installations","")).lower()

        fac, fac_d = _nearest_in_store(FACILITIES_STORE, _FAC_GRID, lat, lng, 1500)
        result["nearest_facility"]        = fac["name"] if fac else None
        result["nearest_facility_dist"]   = fac_d
        result["facilities_1km"]          = _count_within(FACILITIES_STORE, _FAC_GRID, lat, lng, 1000)

        lib, lib_d = _nearest_in_store(FACILITIES_STORE, _FAC_GRID, lat, lng, 2000, is_library)
        result["nearest_library"]         = lib["name"] if lib else None
        result["nearest_library_dist"]    = lib_d

        pool, pool_d = _nearest_in_store(FACILITIES_STORE, _FAC_GRID, lat, lng, 2000, is_pool)
        result["nearest_pool"]            = pool["name"] if pool else None
        result["nearest_pool_dist"]       = pool_d

    # POI density
    if POI_STORE:
        def is_cultural(f): return f.get("famille","").lower() in ("culturel","éducation")
        def is_sport(f): return f.get("famille","").lower() in ("sports et loisirs","sport")

        result["poi_500m"]              = _count_within(POI_STORE, _POI_GRID, lat, lng, 500)
        result["cultural_poi_1km"]      = _count_within(POI_STORE, _POI_GRID, lat, lng, 1000, is_cultural)
        result["sport_poi_1km"]         = _count_within(POI_STORE, _POI_GRID, lat, lng, 1000, is_sport)

    # Commercial density & vacancy
    if COMMERCIAL_STORE:
        def is_vacant(f): return f.get("vacant", 0) == 1
        result["commercial_200m"]       = _count_within(COMMERCIAL_STORE, _COM_GRID, lat, lng, 200)
        result["commercial_500m"]       = _count_within(COMMERCIAL_STORE, _COM_GRID, lat, lng, 500)
        result["vacant_commercial_200m"]= _count_within(COMMERCIAL_STORE, _COM_GRID, lat, lng, 200, is_vacant)

    return result


def cubf_label(code):
    try:
        c=int(code)
        if c in CUBF_LABELS: return CUBF_LABELS[c]
        d=(c//10)*10
        if d in CUBF_LABELS: return CUBF_LABELS[d]
        h=(c//100)*100
        if h in CUBF_LABELS: return CUBF_LABELS[h]
        return f"Code {code}"
    except: return str(code) if code else "Unknown"

def haversine_m(lat1,lng1,lat2,lng2):
    R=6371000
    p1,p2=math.radians(lat1),math.radians(lat2)
    dp,dl=math.radians(lat2-lat1),math.radians(lng2-lng1)
    a=math.sin(dp/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2*R*math.asin(math.sqrt(a))

def nearest_rem(lat,lng):
    if not lat or not lng: return None,None
    best=min(REM_STATIONS,key=lambda s:haversine_m(lat,lng,s["lat"],s["lng"]))
    return best["name"],round(haversine_m(lat,lng,best["lat"],best["lng"]))

def safe_int(v):
    try: return int(str(v).strip()) if v and str(v).strip() not in ("","0","-1") else None
    except: return None

def safe_float(v):
    try: return float(str(v).strip()) if v and str(v).strip() not in ("","-1") else None
    except: return None

def norm(s):
    """Normalize string for fuzzy matching.
    Strips accents, parenthetical qualifiers, extra spaces.
    'avenue Atwater  (MTL+WMT)' → 'avenue atwater'
    """
    if not s: return ""
    s = s.lower().strip()
    # Strip parenthetical borough/zone qualifiers like "(MTL+WMT)", "(MTL)", "(WMT)"
    s = re.sub(r"\s*\([^)]*\)", "", s)
    # Strip accents
    for fr,en in [("é","e"),("è","e"),("ê","e"),("ë","e"),("à","a"),("â","a"),("ä","a"),
                  ("î","i"),("ï","i"),("ô","o"),("ö","o"),("û","u"),("ù","u"),("ü","u"),("ç","c")]:
        s = s.replace(fr, en)
    # Collapse whitespace and hyphens
    return re.sub(r"[\s\-]+", " ", s).strip()

def norm_borough(s):
    """Normalize borough name for centre lookup."""
    if not s: return ""
    n = norm(s)
    # Try direct match
    for key in BOROUGH_CENTRES:
        if norm(key) == n: return key
    # Try partial
    for key in BOROUGH_CENTRES:
        if norm(key) in n or n in norm(key): return key
    return s  # return as-is

def parse_address(addr):
    addr=addr.strip()
    m=re.match(r"^(\d+)\s+(.+)$",addr)
    if m:
        try: return int(m.group(1)),m.group(2).strip()
        except: pass
    return None,addr

def download(url,dest,desc):
    print(f"  Downloading {desc}…")
    dest.parent.mkdir(parents=True,exist_ok=True)
    req=urllib.request.Request(url,headers={"User-Agent":"MTLPropIntel/2.0"})
    with urllib.request.urlopen(req,timeout=180) as r, open(dest,"wb") as f:
        total=int(r.headers.get("Content-Length",0))
        done=0
        while True:
            chunk=r.read(65536)
            if not chunk: break
            f.write(chunk); done+=len(chunk)
            if total: print(f"\r    {done/total*100:.0f}%  ",end="",flush=True)
    print()

# ── STREET QUALIFIER → BOROUGH MAP ───────────────────────────────────────────
# The NOM_RUE field contains abbreviations identifying the borough/municipality.
# e.g. "rue Clark  (MTL)" → Plateau area; "avenue Thornhill  (WMT)" → Westmount
# For single-qualifier streets this is definitive.
# For cross-borough streets like "(MTL+WMT)" we use REM code to pick the right one.

# Abbreviation → canonical borough name
ABBREV_MAP = {
    # Demerged cities — unambiguous
    "WMT":  "Westmount",
    "MTR":  "Mont-Royal",
    "OUT":  "Outremont",
    "CSL":  "Cote-Saint-Luc",
    "HMS":  "Hampstead",
    "DDO":  "Dollard-Des-Ormeaux",
    "DVL":  "Dorval",
    "PCL":  "Pointe-Claire",
    "KRK":  "Kirkland",
    "BCF":  "Beaconsfield",
    "BDU":  "Baie-D-Urfe",
    "SNV":  "Senneville",
    "SBL":  "Sainte-Anne-de-Bellevue",
    "MTE":  "Montreal-Est",
    "MTO":  "Montreal-Ouest",
    "IDO":  "L-Ile-Dorval",
    # Arrondissements — unambiguous abbreviations
    "ANJ":  "Anjou",
    "VRD":  "Verdun",
    "SLR":  "Saint-Laurent",
    "LSL":  "LaSalle",
    "LCH":  "Lachine",
    "PFD":  "Pierrefonds-Roxboro",
    "IBZ":  "L-Ile-Bizard-Sainte-Genevieve",
    "RDP":  "Riviere-des-Prairies-Pointe-aux-Trembles",
    "PAT":  "Riviere-des-Prairies-Pointe-aux-Trembles",
    "PTE":  "Riviere-des-Prairies-Pointe-aux-Trembles",  # Pointe-aux-Trembles variant
    "MTN":  "Montreal-Nord",
    "SLN":  "Saint-Leonard",
    "MHM":  "Mercier-Hochelaga-Maisonneuve",
    "AHU":  "Ahuntsic-Cartierville",
    "AHC":  "Ahuntsic-Cartierville",
}

# REM code → borough for properties where NOM_RUE only has "(MTL)"
# Derived from street examples in the actual CSV data:
# REM05 → Outremont (rue Hutchison crosses MTL+OUT — REM05 is the Outremont portion)
# REM12 → Verdun
# REM15 → Saint-Laurent
# REM17 → LaSalle
# REM19 → Le Sud-Ouest / Ville-Marie boundary (Atwater area)
# REM20 → Le Sud-Ouest (rue Holy Cross)
# REM21 → Le Plateau-Mont-Royal (rue Clark)
# REM22 → Ahuntsic-Cartierville (rue Arcand)
# REM23 → Rosemont-La Petite-Patrie (avenue Papineau)
# REM24 → Rosemont-La Petite-Patrie (rue Masson)
# REM25 → Villeray-Saint-Michel-Parc-Extension (rue de Liège Ouest)
# REM27 → Lachine (avenue Vincent)
# REM31 → Pierrefonds-Roxboro
# REM32 → L-Ile-Bizard-Sainte-Genevieve
# REM33 → Mercier-Hochelaga-Maisonneuve (rue de la Famille-Dubreuil)
# REM34 → Cote-des-Neiges-Notre-Dame-de-Grace (chemin de la Côte-des-Neiges)
# REM99 → Westmount (MUNICIPALITE=29)
# REM09 → Anjou
# REM16 → split Montreal-Nord / Villeray area (boulevard Saint-Michel)
# REM14 → split Montreal-Nord / Saint-Laurent (boulevard Langelier)

REM_BOROUGH_MAP = {
    "REM05":  "Outremont",
    "REM09":  "Anjou",
    "REM12":  "Verdun",
    "REM14":  "Saint-Laurent",
    "REM15":  "Saint-Laurent",
    "REM16":  "Villeray-Saint-Michel-Parc-Extension",
    "REM17":  "LaSalle",
    "REM19":  "Ville-Marie",
    "REM20":  "Le Sud-Ouest",
    "REM21":  "Le Plateau-Mont-Royal",
    "REM22":  "Ahuntsic-Cartierville",
    "REM23":  "Rosemont-La Petite-Patrie",
    "REM24":  "Rosemont-La Petite-Patrie",
    "REM25":  "Villeray-Saint-Michel-Parc-Extension",
    "REM27":  "Lachine",
    "REM31":  "Pierrefonds-Roxboro",
    "REM32":  "L-Ile-Bizard-Sainte-Genevieve",
    "REM33":  "Mercier-Hochelaga-Maisonneuve",  # low civics; high civics may be RDP
    "REM34":  "Cote-des-Neiges-Notre-Dame-de-Grace",
    "REM99":  "Westmount",
}

def extract_borough_from_rue(rue_raw, rem_code, mun_raw="", civic_num=None):
    """
    Extract borough from the NOM_RUE qualifier abbreviation.
    e.g. "rue Clark  (MTL)"     + REM21 → Le Plateau-Mont-Royal
    e.g. "avenue Thornhill  (WMT)"      → Westmount (unambiguous)
    e.g. "avenue Atwater  (MTL+WMT)"   → Ville-Marie (via REM code)
    e.g. "rue Sylvain-Garneau  (RDP)"   → Rivière-des-Prairies-PAT
    e.g. "rue Sylvain-Garneau  (MTL+RDP)" → Rivière-des-Prairies-PAT
    """
    import re as _re
    m = _re.search(r"\(([A-Z]{2,4}(?:\+[A-Z]{2,4})*)\)", rue_raw or "")
    if not m:
        return REM_BOROUGH_MAP.get(rem_code, "")

    qualifier = m.group(1)
    parts = qualifier.split("+")

    # Single unambiguous abbreviation
    if len(parts) == 1:
        abbrev = parts[0]
        if abbrev in ABBREV_MAP:
            return ABBREV_MAP[abbrev]
        if abbrev == "MTL":
            return REM_BOROUGH_MAP.get(rem_code, "")
        return ""

    # Multiple abbreviations — find non-MTL ones
    non_mtl = [p for p in parts if p != "MTL" and p in ABBREV_MAP]
    if len(non_mtl) == 1:
        # One clear borough besides MTL — use it directly
        return ABBREV_MAP[non_mtl[0]]

    # Multiple non-MTL or all MTL — use REM code
    rem_borough = REM_BOROUGH_MAP.get(rem_code, "")
    if rem_borough:
        return rem_borough

    # Last resort: first non-MTL abbreviation
    for p in parts:
        if p != "MTL" and p in ABBREV_MAP:
            return ABBREV_MAP[p]
    return ""


def build_properties_db():
    csv_path=SOURCES["assessment"]["path"]
    if not csv_path.exists():
        download(SOURCES["assessment"]["url"],csv_path,SOURCES["assessment"]["desc"])

    print("  Building property index (~60 seconds)…")
    conn=sqlite3.connect(DB_PATH)
    c=conn.cursor()
    c.executescript("""
        DROP TABLE IF EXISTS properties;
        CREATE TABLE properties (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            matricule    TEXT,
            civic_start  INTEGER,
            civic_end    INTEGER,
            street       TEXT,
            street_norm  TEXT,
            suite        TEXT,
            borough      TEXT,
            year_built   INTEGER,
            cubf_code    INTEGER,
            cubf_label   TEXT,
            nb_logements INTEGER,
            nb_etages    INTEGER,
            lot_m2       REAL,
            bldg_m2      REAL,
            categorie    TEXT,
            full_address TEXT
        );
        CREATE INDEX idx_sn   ON properties(street_norm);
        CREATE INDEX idx_civ  ON properties(civic_start);
        CREATE INDEX idx_mat  ON properties(matricule);
        CREATE INDEX idx_bor  ON properties(borough);
        CREATE INDEX idx_cub  ON properties(cubf_code);
    """)

    # Peek at CSV headers
    with open(csv_path,encoding="utf-8",errors="replace") as f:
        sample=f.readline()
    sep=";" if sample.count(";")>sample.count(",") else ","
    print(f"    Detected separator: '{sep}'")

    inserted=0; batch=[]
    with open(csv_path,encoding="utf-8",errors="replace") as f:
        reader=csv.DictReader(f,delimiter=sep)
        for row in reader:
            try:
                street=(row.get("NOM_RUE") or "").strip()
                cs=safe_int(row.get("CIVIQUE_DEBUT"))  # None if absent
                ce=safe_int(row.get("CIVIQUE_FIN")) or cs

                # Borough extraction — use the street name qualifier (most reliable source).
                # NOM_RUE contains abbreviations like "(MTL)", "(ANJ)", "(VRD)" which are
                # the actual borough/city codes embedded by the assessor.
                # For cross-borough streets like "(MTL+WMT)", use the REM code to
                # disambiguate based on which borough the property actually sits in.
                _rue_raw    = row.get("NOM_RUE") or ""
                _rem_code   = (row.get("NO_ARROND_ILE_CUM") or "").strip()
                _mun_raw    = str(row.get("MUNICIPALITE") or "").strip()
                _civic_num  = safe_int(row.get("CIVIQUE_DEBUT") or row.get("CIVIQUE_DE"))
                borough     = extract_borough_from_rue(_rue_raw, _rem_code, _mun_raw, _civic_num)

                cubf=safe_int(row.get("CODE_UTILISATION")) or 0
                # Use CSV's own description if our map would just say "Code XXXX"
                _csv_label=(row.get("LIBELLE_UTILISATION") or "").strip()
                # Build readable address
                lettre=(row.get("LETTRE_DEBUT") or "").strip()
                # Strip parenthetical qualifiers from street for display
                street_display = re.sub(r"\s*\([^)]*\)", "", street).strip()
                if cs and cs > 0:
                    civic_str = str(cs) + lettre  # e.g. "3577A"
                    full = f"{civic_str} {street_display}".strip()
                else:
                    full = street_display.strip()
                # Store suite separately — don't embed in address (breaks geocoding)
                _suite = (row.get("SUITE_DEBUT") or "").strip()

                batch.append((
                    (row.get("MATRICULE83") or row.get("MATRICULE") or "").strip(),
                    cs, ce, street, norm(street),
                    (row.get("SUITE_DEBUT") or "").strip(),
                    borough,
                    safe_int(row.get("ANNEE_CONSTRUCTION")),
                    cubf, _csv_label or cubf_label(cubf),
                    safe_int(row.get("NOMBRE_LOGEMENT")),
                    safe_int(row.get("ETAGE_HORS_SOL")),
                    safe_float(row.get("SUPERFICIE_TERRAIN")),
                    safe_float(row.get("SUPERFICIE_BATIMENT")),
                    (row.get("CATEGORIE_UEF") or "").strip(),
                    full,
                ))
                inserted+=1
                if len(batch)>=5000:
                    c.executemany("""INSERT INTO properties(
                        matricule,civic_start,civic_end,street,street_norm,suite,
                        borough,year_built,cubf_code,cubf_label,nb_logements,nb_etages,
                        lot_m2,bldg_m2,categorie,full_address
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",batch)
                    conn.commit(); batch=[]
                    print(f"\r  {inserted:,} rows…  ",end="",flush=True)
            except Exception: pass

    if batch:
        c.executemany("""INSERT INTO properties(
            matricule,civic_start,civic_end,street,street_norm,suite,
            borough,year_built,cubf_code,cubf_label,nb_logements,nb_etages,
            lot_m2,bldg_m2,categorie,full_address
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",batch)
        conn.commit()

    # Report what NO_ARROND_ILE_CUM and MUNICIPALITE values actually appeared
    c.execute("SELECT borough, COUNT(*) FROM properties WHERE borough!=\'\' GROUP BY borough ORDER BY 2 DESC LIMIT 20")
    borough_rows = c.fetchall()
    top5 = [(r[0],r[1]) for r in borough_rows[:5]]
    print(f"  Boroughs found: {top5}…")
    
    c.execute("SELECT COUNT(*) FROM properties WHERE borough IS NULL OR borough=''")
    missing = c.fetchone()[0]
    print(f"  Properties with NO borough: {missing:,}")

    # Sample the raw NO_ARROND_ILE_CUM and MUNICIPALITE to debug borough issues
    # Read first 5 distinct values from the CSV
    with open(csv_path, encoding="utf-8", errors="replace") as f2:
        reader2 = csv.DictReader(f2, delimiter=sep)
        samples = []
        for i, row in enumerate(reader2):
            if i >= 100: break
            samples.append((
                row.get("NO_ARROND_ILE_CUM","?"),
                row.get("MUNICIPALITE","?"),
                row.get("NOM_ARROND","?"),
                row.get("NOM_RUE","?")[:30],
            ))
    # Show distinct NO_ARROND_ILE_CUM values
    distinct_codes = list({s[0] for s in samples})[:10]
    distinct_mun   = list({s[1] for s in samples})[:10]
    print(f"  Sample NO_ARROND_ILE_CUM values: {distinct_codes}")
    print(f"  Sample MUNICIPALITE values: {distinct_mun}")
    print(f"  NOM_ARROND present: {any(s[2] for s in samples)}")

    conn.close()
    print(f"  Indexed {inserted:,} properties")

def build_permits_db():
    csv_path=SOURCES["permits"]["path"]
    if not csv_path.exists():
        download(SOURCES["permits"]["url"],csv_path,SOURCES["permits"]["desc"])

    print("  Building permit index…")
    conn=sqlite3.connect(DB_PATH)
    c=conn.cursor()
    c.executescript("""
        DROP TABLE IF EXISTS permits;
        CREATE TABLE permits(
            id          INTEGER PRIMARY KEY,
            no_permis   TEXT,
            date_deliv  TEXT,
            arrond      TEXT,
            norm_arrond TEXT,
            civic       INTEGER,
            street      TEXT,
            street_norm TEXT,
            categorie   TEXT,
            nature_travaux TEXT,
            description TEXT,
            valeur      REAL
        );
        CREATE INDEX idx_ps ON permits(street_norm);
        CREATE INDEX idx_pa ON permits(norm_arrond);
    """)

    with open(csv_path,encoding="utf-8",errors="replace") as f:
        sample=f.readline()
    sep=";" if sample.count(";")>sample.count(",") else ","

    count=0; batch=[]
    with open(csv_path,encoding="utf-8",errors="replace") as f:
        reader=csv.DictReader(f,delimiter=sep)
        for row in reader:
            try:
                # Montreal permits CSV actual columns:
                # emplacement (civic + street), arrondissement, nature_travaux,
                # description_type_demande, id_permis, date_emission, latitude, longitude
                emplacement=(row.get("emplacement") or "").strip()
                m=re.match(r"^\s*(\d+)\s+(.+)$", emplacement)
                civic_num=safe_int(m.group(1)) if m else safe_int(row.get("NO_CIVIQUE"))
                street_raw=m.group(2).strip() if m else (row.get("NOM_RUE") or emplacement).strip()
                arrond=(row.get("arrondissement") or row.get("NOM_ARROND") or "").strip()
                cat=(row.get("description_type_demande") or row.get("_CATEGORIE") or "").strip()
                desc=(row.get("nature_travaux") or row.get("_TRAVAUX") or "").strip()
                # Use date_emission as the delivery date
                date_val=(row.get("date_emission") or row.get("DATE_DELIVRANCE") or "").strip()
                nature=(row.get("nature_travaux") or "").strip()
                batch.append((
                    (row.get("id_permis") or row.get("NO_PERMIS") or "").strip(),
                    date_val,
                    arrond, norm(arrond),
                    civic_num,
                    street_raw, norm(street_raw),
                    cat, nature, desc,
                    safe_float(row.get("VALEUR_TRAVAUX") or row.get("valeur")),
                ))
                count+=1
                if len(batch)>=5000:
                    c.executemany("INSERT INTO permits(no_permis,date_deliv,arrond,norm_arrond,civic,street,street_norm,categorie,nature_travaux,description,valeur) VALUES(?,?,?,?,?,?,?,?,?,?,?)",batch)
                    conn.commit(); batch=[]
            except Exception: pass
    if batch:
        c.executemany("INSERT INTO permits(no_permis,date_deliv,arrond,norm_arrond,civic,street,street_norm,categorie,nature_travaux,description,valeur) VALUES(?,?,?,?,?,?,?,?,?,?,?)",batch)
        conn.commit()
    conn.close()
    print(f"  Indexed {count:,} permits")

CONTAMINATED=[]
AMENITIES_LOADED=False

def load_contaminated():
    path=SOURCES["contaminated"]["path"]
    if not path.exists():
        try: download(SOURCES["contaminated"]["url"],path,SOURCES["contaminated"]["desc"])
        except Exception as e: print(f"  Contaminated unavailable: {e}"); return []
    try:
        with open(path) as f: data=json.load(f)
        return data if isinstance(data,list) else data.get("data",[])
    except: return []

def get_rem(borough):
    bc=BOROUGH_CENTRES.get(norm_borough(borough),(None,None))
    return nearest_rem(*bc)

# estimate_value() is now defined above in the market rate engine section


# ── MARKET RATE ENGINE ────────────────────────────────────────────────────────

def cubf_group(cubf, units=None):
    """
    Map CUBF code to property group for valuation.
    Unit count (NOMBRE_LOGEMENT) overrides CUBF when available — many pre-1960
    plexes carry CUBF 1000 (single-family) because that was the original classification.
    """
    units = units or 0
    # Unit count is authoritative
    if units >= 6:  return "multi"
    if units >= 2:  return "plex"
    # Fall back to CUBF
    if not cubf: return "single_family"
    c = int(cubf) if str(cubf).isdigit() else 0
    if c < 1010: return "single_family"
    if c < 1100: return "plex"
    if c < 2000: return "multi"
    if c < 3000: return "commercial"
    return "other"

def norm_borough_for_market(borough):
    """Normalize borough name to canonical form for QPAREB_MEDIANS lookup."""
    if not borough: return ""
    b = borough.strip().lower()
    for fr, en in [("é","e"),("è","e"),("ê","e"),("ë","e"),("î","i"),("ï","i"),
                   ("ô","o"),("ö","o"),("û","u"),("ù","u"),("ü","u"),("ç","c"),
                   ("à","a"),("â","a"),("æ","e")]:
        b = b.replace(fr, en)
    b = re.sub(r'[\s\-/.,]+', " ", b).strip()
    b = re.sub(r"\s+", " ", b)

    MAP = {
        # Le Plateau-Mont-Royal
        "plateau mont royal": "Le Plateau-Mont-Royal",
        "le plateau mont royal": "Le Plateau-Mont-Royal",
        "plateau": "Le Plateau-Mont-Royal",
        # Rosemont-La Petite-Patrie
        "rosemont la petite patrie": "Rosemont-La Petite-Patrie",
        "rosemont petite patrie": "Rosemont-La Petite-Patrie",
        "rosemont": "Rosemont-La Petite-Patrie",
        # Villeray-Saint-Michel-Parc-Extension
        "villeray saint michel parc extension": "Villeray-Saint-Michel-Parc-Extension",
        "villeray": "Villeray-Saint-Michel-Parc-Extension",
        "saint michel": "Villeray-Saint-Michel-Parc-Extension",
        "parc extension": "Villeray-Saint-Michel-Parc-Extension",
        # CDN-NDG
        "cote des neiges notre dame de grace": "Cote-des-Neiges-Notre-Dame-de-Grace",
        "cote des neiges ndg": "Cote-des-Neiges-Notre-Dame-de-Grace",
        "cote des neiges": "Cote-des-Neiges-Notre-Dame-de-Grace",
        "notre dame de grace": "Cote-des-Neiges-Notre-Dame-de-Grace",
        "cdn ndg": "Cote-des-Neiges-Notre-Dame-de-Grace",
        "cdn": "Cote-des-Neiges-Notre-Dame-de-Grace",
        # Mercier-Hochelaga-Maisonneuve
        "mercier hochelaga maisonneuve": "Mercier-Hochelaga-Maisonneuve",
        "hochelaga maisonneuve": "Mercier-Hochelaga-Maisonneuve",
        "hochelaga": "Mercier-Hochelaga-Maisonneuve",
        "mercier": "Mercier-Hochelaga-Maisonneuve",
        # Ahuntsic-Cartierville
        "ahuntsic cartierville": "Ahuntsic-Cartierville",
        "ahuntsic": "Ahuntsic-Cartierville",
        "cartierville": "Ahuntsic-Cartierville",
        # Rivière-des-Prairies-Pointe-aux-Trembles
        "riviere des prairies pointe aux trembles": "Riviere-des-Prairies-Pointe-aux-Trembles",
        "riviere des prairies": "Riviere-des-Prairies-Pointe-aux-Trembles",
        "pointe aux trembles": "Riviere-des-Prairies-Pointe-aux-Trembles",
        "rdp pat": "Riviere-des-Prairies-Pointe-aux-Trembles",
        # Ville-Marie
        "ville marie": "Ville-Marie",
        "centre ville": "Ville-Marie",
        "old montreal": "Ville-Marie",
        "vieux montreal": "Ville-Marie",
        # Le Sud-Ouest
        "le sud ouest": "Le Sud-Ouest",
        "sud ouest": "Le Sud-Ouest",
        "pointe saint charles": "Le Sud-Ouest",
        "saint henri": "Le Sud-Ouest",
        "little burgundy": "Le Sud-Ouest",
        # Others
        "saint laurent": "Saint-Laurent",
        "saint leonard": "Saint-Leonard",
        "montreal nord": "Montreal-Nord",
        "l ile bizard sainte genevieve": "L-Ile-Bizard-Sainte-Genevieve",
        "ile bizard": "L-Ile-Bizard-Sainte-Genevieve",
        "pierrefonds roxboro": "Pierrefonds-Roxboro",
        "pierrefonds": "Pierrefonds-Roxboro",
        "roxboro": "Pierrefonds-Roxboro",
        "dollard des ormeaux": "Dollard-Des-Ormeaux",
        "ddo": "Dollard-Des-Ormeaux",
        "cote saint luc": "Cote-Saint-Luc",
        "mont royal": "Mont-Royal",
        "town of mount royal": "Mont-Royal",
        "tmr": "Mont-Royal",
        "montreal est": "Montreal-Est",
        "montreal ouest": "Montreal-Ouest",
        "pointe claire": "Pointe-Claire",
        "sainte anne de bellevue": "Sainte-Anne-de-Bellevue",
        "baie d urfe": "Baie-D-Urfe",
        "baie durfe": "Baie-D-Urfe",
    }
    result = MAP.get(b)
    if result: return result
    # Try prefix matching
    for k, v in MAP.items():
        if len(k) > 6 and b.startswith(k[:8]):
            return v
    # "Montreal" (bare city name) means arrondissement wasn't resolved —
    # return empty so we fall through to island-wide rates
    if b in ("montreal", "ville de montreal", "agglomeration de montreal"):
        return ""
    return borough.strip()

def build_market_rates():
    """
    Download 2023 and 2024 Montreal real estate transaction CSVs.
    Parse sale amounts by arrondissement and property category.
    Build per-m² price benchmarks to calibrate the valuation model.

    The transactions CSV contains:
      - montant_transaction (sale amount)
      - arrondissement
      - categorie (property category text)
      - description (includes property type info)

    Since the transactions CSV doesn't include property dimensions,
    we compute median price per transaction and median price by category,
    then use the assessment roll's dimension data to derive per-m² rates
    using the relationship: median_price = land_rate × avg_lot + build_rate × avg_bldg
    """
    global MARKET_RATES, MARKET_RATES_LOADED, TRANSACTIONS_LOADED

    all_transactions = []

    for key in ["transactions_2023", "transactions_2024"]:
        src = SOURCES[key]
        if not src["path"].exists():
            try:
                download(src["url"], src["path"], src["desc"])
            except Exception as e:
                print(f"  {key}: download failed: {e}")
                continue

        try:
            with open(src["path"], encoding="utf-8", errors="replace") as f:
                sample = f.readline()
            sep = ";" if sample.count(";") > sample.count(",") else ","

            rows_in_mem = []
            with open(src["path"], encoding="utf-8", errors="replace") as f:
                reader = csv.DictReader(f, delimiter=sep)
                if reader.fieldnames:
                    reader.fieldnames = [
                        (col or "").replace("\xa0","").replace("\u00a0","").strip()
                        for col in reader.fieldnames
                    ]
                print(f"  {key} columns: {(reader.fieldnames or [])[:8]}")
                rows_in_mem = list(reader)

            for row in rows_in_mem:
                        # Find the amount column — try multiple name variants
                    try:
                        amount = None
                        # Try known column names first
                        for col in ["montant_transaction","montant","MONTANT",
                                    "MONTANT_TRANSACTION","amount","valeur","Montant"]:
                            raw = (row.get(col) or row.get(col.lower()) or "")
                            v = str(raw).strip().replace(" ","").replace(" ","").replace(" ","").replace(",",".").replace("$","")
                            if v and v.replace(".","").replace("-","").isdigit():
                                try: amount = float(v); break
                                except: pass
                        # If still no amount, scan all columns for a numeric > 10000
                        if not amount:
                            for col, raw in row.items():
                                v = str(raw or "").strip().replace(" ","").replace(" ","").replace(" ","").replace(",",".").replace("$","")
                                if v and len(v) >= 5 and v.replace(".","").replace("-","").isdigit():
                                    try:
                                        n = float(v)
                                        if 10000 < n < 50000000:  # realistic property price range
                                            amount = n; break
                                    except: pass
                        if not amount or amount < 10000: continue

                        arrond = (row.get("arrondissement") or row.get("ARRONDISSEMENT") or "").strip()
                        # Strip NBSP from arrond too
                        arrond = arrond.replace(" ","").strip()
                        categorie = (row.get("categorie") or row.get("Catégorie") or row.get("CATEGORIE") or row.get("description_type_batiment") or "").strip().lower()
                        categorie = categorie.replace(" ","").strip()

                        # Map category text to cubf_group
                        if any(w in categorie for w in ["résidentiel","residential","logement"]):
                            if any(w in categorie for w in ["multi","appartement","immeuble"]):
                                grp = "multi"
                            elif any(w in categorie for w in ["plex","duplex","triplex"]):
                                grp = "plex"
                            else:
                                grp = "single_family"
                        elif any(w in categorie for w in ["commercial","bureau","industriel"]):
                            grp = "commercial"
                        else:
                            grp = "other"

                        all_transactions.append({
                            "amount": amount,
                            "arrond": arrond,
                            "group": grp,
                        })
                    except Exception: pass

            print(f"  {key}: {len(all_transactions)} transactions so far")
        except Exception as e:
            print(f"  {key}: parse error: {e}")
            import traceback; traceback.print_exc()

    if not all_transactions:
        print("  No transactions loaded — keeping fallback rates")
        return

    TRANSACTIONS_LOADED = len(all_transactions)

    # Compute median price by borough × property group
    from statistics import median
    bucket = {}  # (arrond_norm, group) → [amounts]
    for t in all_transactions:
        arrond = norm_borough_for_market(t["arrond"])
        key = (arrond, t["group"])
        if key not in bucket: bucket[key] = []
        bucket[key].append(t["amount"])

    # Also compute by group only (island-wide fallback)
    island_bucket = {}
    for t in all_transactions:
        g = t["group"]
        if g not in island_bucket: island_bucket[g] = []
        island_bucket[g].append(t["amount"])

    rates = {}

    # Load assessment roll averages to derive per-m² rates
    # avg_lot and avg_bldg by borough from our DB
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("""
            SELECT borough,
                   AVG(CASE WHEN lot_m2 > 0 THEN lot_m2 END) as avg_lot,
                   AVG(CASE WHEN bldg_m2 > 0 THEN bldg_m2 END) as avg_bldg,
                   COUNT(*) as n
            FROM properties
            WHERE borough != '' AND lot_m2 > 0
            GROUP BY borough
        """)
        avg_dims = {r[0]: {"avg_lot":r[1] or 200, "avg_bldg":r[2] or 120, "n":r[3]} for r in c.fetchall()}
        conn.close()
    except Exception:
        avg_dims = {}

    # Island-wide fallback medians
    island_medians = {g: median(v) for g, v in island_bucket.items() if len(v) >= 5}

    for (arrond, grp), amounts in bucket.items():
        if len(amounts) < 3: continue  # need at least 3 sales
        med = median(amounts)
        dims = avg_dims.get(arrond, {"avg_lot":200,"avg_bldg":120})

        # Derive land rate: med_price = land_rate × avg_lot + 900 × avg_bldg (rough bldg cost)
        # Solving for land_rate: (med - 900 × avg_bldg) / avg_lot
        bldg_cost_est = 900  # conservative construction cost $/m² for existing stock
        land_rate = max(400, (med - bldg_cost_est * dims["avg_bldg"]) / max(dims["avg_lot"], 50))

        if arrond not in rates: rates[arrond] = {}
        rates[arrond][grp] = {
            "median_price":   round(med),
            "land_rate":      round(land_rate),
            "sample_n":       len(amounts),
            "derived_from":   "2023-2024 transactions",
        }

    # Island-wide rates for boroughs with insufficient transaction data
    island_rates = {}
    for grp, amounts in island_bucket.items():
        if len(amounts) < 10: continue
        med = median(amounts)
        land_rate = max(400, (med - 900 * 120) / 200)  # island avg dimensions
        island_rates[grp] = {
            "median_price": round(med),
            "land_rate":    round(land_rate),
            "sample_n":     len(amounts),
            "derived_from": "2023-2024 island-wide",
        }

    # Supplement QPAREB_MEDIANS with transaction-derived medians where we have
    # enough sample size — transactions CSV gives us actual sold prices vs broker estimates
    supplemented = 0
    for (arrond, grp), amounts in bucket.items():
        if len(amounts) < 10: continue   # need decent sample before overriding QPAREB
        med = median(amounts)
        # Only use if it's plausibly a real sale (not servitude/easement)
        if med < 50000: continue
        b_canon = norm_borough_for_market(arrond)
        # Map grp to QPAREB type
        qtype = {"single_family":"single_family","plex":"plex","multi":"multi"}.get(grp,"single_family")
        if b_canon in QPAREB_MEDIANS:
            old_val = QPAREB_MEDIANS[b_canon].get(qtype, 0)
            # Blend: 70% QPAREB (quarterly aggregate) + 30% transactions CSV (smaller but fresher)
            QPAREB_MEDIANS[b_canon][qtype] = round(old_val * 0.70 + med * 0.30)
            supplemented += 1

    MARKET_RATES = {"by_borough": rates, "island_wide": island_rates}
    MARKET_RATES_LOADED = True

    n_boroughs = len(rates)
    n_buckets  = sum(len(v) for v in rates.values())
    print(f"  ✓ Market rates: {TRANSACTIONS_LOADED:,} transactions processed")
    print(f"    Supplemented {supplemented} QPAREB median buckets with transaction data")
    print(f"    {n_boroughs} boroughs with transaction rate data, {n_buckets} buckets")

def estimate_value(borough, r):
    """
    Multi-source valuation model — three independent estimates, then blended.

    Method A — QPAREB comparable median (primary for residential):
      Borough × property-type median price from QPAREB/Centris Q4 2025 data.
      Adjusted for property size relative to borough average.
      Source: QPAREB residential barometer Q4 2025, Centris broker database.

    Method B — Income capitalisation (primary for 4+ unit income properties):
      NOI = units × CMHC average monthly rent × 12 × (1 - 0.35 opex)
      Value = NOI / cap_rate
      Sources: CMHC Rental Market Report Montreal CMA 2024,
               QPAREB/JLR cap rate benchmarks 2024.

    Method C — Cost approach (land + depreciated replacement cost):
      Land value = lot_m2 × implied land rate from QPAREB medians
      Building value = bldg_m2 × CMHC replacement cost × age_factor
      Source: CMHC construction cost data 2024 (~$3,500/m² new residential)

    Blend weights vary by property type:
      Single-family / condo: 60% QPAREB comparable + 40% cost
      Plex (2-5 units): 50% QPAREB comparable + 30% income + 20% cost
      Multi (6+ units): 20% QPAREB comparable + 65% income + 15% cost

    Uncertainty: ±15% when QPAREB median available, ±25% island-wide fallback.
    All figures in CAD. Not a formal appraisal. Cross-reference with Evalweb.
    """
    lot   = r.get("lot_m2")  or 0
    bldg  = r.get("bldg_m2") or 0
    yr    = r.get("year_built") or 1970
    units = r.get("nb_logements") or 1
    cubf  = r.get("cubf_code") or 0
    grp   = cubf_group(cubf, units)   # units override CUBF for plex/multi

    if lot == 0 and bldg == 0:
        return None

    b = norm_borough_for_market(borough)

    # ── Age depreciation factor ──────────────────────────────────────────────
    # Based on Quebec MEFQ depreciation tables — economic life 60-80 yrs residential.
    if   yr >= 2015: age_f = 1.00
    elif yr >= 2005: age_f = 0.92
    elif yr >= 1995: age_f = 0.82
    elif yr >= 1980: age_f = 0.68
    elif yr >= 1960: age_f = 0.52
    elif yr >= 1940: age_f = 0.40
    else:            age_f = 0.32   # pre-1940 — land dominates value

    # ── Method A: QPAREB comparable median ───────────────────────────────────
    # Map CUBF group to QPAREB property type
    qpareb_type = {
        "single_family": "single_family",
        "plex":          "plex",
        "multi":         "multi",
        "commercial":    "single_family",  # no commercial median — use sf as placeholder
        "other":         "single_family",
    }.get(grp, "single_family")
    # Use condo type for:
    # - CUBF 9100+ (explicit condo classification)
    # - Category = "Condominium" / "CON" in assessment roll
    # - 1 unit with very small "lot" (<80m²) — the lot field for condos is
    #   their proportional share of the land, not a real parcel
    categorie = (r.get("categorie") or "").strip().upper()
    is_condo = (
        (cubf and int(str(cubf)[:2]) == 91) or
        categorie in ("CON", "CONDOMINIUM") or
        (units <= 1 and lot <= 80 and lot > 0)
    )
    if is_condo:
        qpareb_type = "condo"

    borough_medians = QPAREB_MEDIANS.get(b) or QPAREB_MEDIANS.get("_island")
    median_price    = borough_medians.get(qpareb_type) or borough_medians.get("single_family")
    qpareb_source   = b if b in QPAREB_MEDIANS else "_island"
    has_qpareb      = qpareb_source != "_island"

    # Size adjustment relative to borough typical property
    # Typical dimensions derived from Montreal assessment roll averages
    # Borough-specific typical condo unit sizes (m²)
    CONDO_TYPICAL_BY_BOROUGH = {
        "Ville-Marie": 65, "Le Plateau-Mont-Royal": 72, "Le Sud-Ouest": 70,
        "Rosemont-La Petite-Patrie": 72, "Villeray-Saint-Michel-Parc-Extension": 70,
        "Cote-des-Neiges-Notre-Dame-de-Grace": 75, "Outremont": 80,
        "Westmount": 85, "Mont-Royal": 85,
        "Pierrefonds-Roxboro": 95, "Ahuntsic-Cartierville": 80,
        "Saint-Laurent": 82, "Mercier-Hochelaga-Maisonneuve": 68,
        "Verdun": 70, "LaSalle": 80, "Lachine": 75,
    }
    condo_typical = CONDO_TYPICAL_BY_BOROUGH.get(b, 75)

    TYPICAL = {
        "single_family": {"lot": 270, "bldg": 140},
        "plex":          {"lot": 260, "bldg": 240},
        "multi":         {"lot": 450, "bldg": 650},
        "condo":         {"lot": 0,   "bldg": condo_typical},
    }
    typ = TYPICAL.get(qpareb_type, TYPICAL["single_family"])
    if qpareb_type == "condo":
        # For condos in the assessment roll:
        # - lot_m2 = proportional land share (unit's share of total land)
        # - bldg_m2 = TOTAL building gross area, not the unit's area
        # - nb_etages = number of floors in the BUILDING, not the unit
        #
        # Best unit area estimate: lot_share × (bldg / lot) gives total floor area
        # relative to unit's land share. Do NOT divide by floors — nb_etages is the
        # building height, not a unit multiplier.
        # e.g. lot=82, bldg=78: unit ≈ 82 × (78/82) = 78m² (makes sense for 1 floor unit)
        # e.g. lot=104, bldg=165: unit ≈ 104 × (165/104) = 165m², capped to 130m²
        if lot > 0 and bldg > 0:
            unit_area_est = lot * (bldg / lot)   # = bldg (land share × density)
            unit_area_est = max(30, min(unit_area_est, 160))  # 30-160m² realistic
        elif bldg > 0:
            unit_area_est = min(bldg, 140)
        elif lot > 0:
            unit_area_est = min(lot, 140)
        else:
            unit_area_est = typ["bldg"]
        size_adj = unit_area_est / typ["bldg"]
    elif lot == 0 and bldg > 0:
        size_adj = bldg / typ["bldg"]
    elif lot > 0 and bldg == 0:
        size_adj = lot / typ["lot"]
    else:
        lot_adj  = (lot / typ["lot"])   if typ["lot"] > 0  else 1.0
        bldg_adj = (bldg / typ["bldg"]) if typ["bldg"] > 0 else 1.0
        size_adj = lot_adj * 0.55 + bldg_adj * 0.45
    # Tighter damping — most Montreal properties are within 50% of typical
    # Tighter clamping for condos — unit area estimates are less reliable
    if qpareb_type == "condo":
        size_adj = max(0.5, min(1.5, size_adj))   # ±50% of typical
    else:
        size_adj = max(0.5, min(1.8, size_adj))   # ±80% for houses/plexes
    # Method A: comparable median adjusted for size only.
    # age_f is NOT applied here — the QPAREB median already reflects the
    # market value of properties of all ages as buyers actually pay.
    # A 1900 Plateau triplex sells at market price, not at a depreciation discount.
    method_a = median_price * size_adj

    # ── Method B: Income capitalisation ──────────────────────────────────────
    cap     = QPAREB_CAP_RATES.get(b, QPAREB_CAP_RATES["_default"])
    rent_mo = CMHC_AVG_RENT_MONTHLY.get(b, CMHC_AVG_RENT_MONTHLY["_default"])
    if units >= 2:
        gross_annual = units * rent_mo * 12
        noi          = gross_annual * 0.65   # 35% vacancy + opex (Montreal plex norm)
        method_b     = noi / (cap / 100)
    else:
        method_b = None

    # ── Method C: Cost approach ───────────────────────────────────────────────
    # Implied land rate from QPAREB median minus typical building replacement cost
    base_bldg_cost = 3500   # $/m² new residential (CMHC 2024)
    bldg_replacement = bldg * base_bldg_cost * age_f
    if lot > 0 and typ["lot"] > 0:
        implied_land_total = median_price - bldg_replacement * (typ["bldg"] / max(bldg,1))
        land_rate          = max(300, implied_land_total / typ["lot"])
    else:
        land_rate = 1600   # $/m² fallback
    method_c = lot * land_rate + bldg_replacement

    # ── Blend by property type ────────────────────────────────────────────────
    if grp == "multi" and method_b:
        base = method_a * 0.20 + method_b * 0.65 + method_c * 0.15
        method_str = "QPAREB comparable 20% + income (CMHC/cap) 65% + cost 15%"
    elif grp == "plex" and method_b:
        # Duplex/triplex: buyer considers both comparable sales and rental income
        base = method_a * 0.45 + method_b * 0.40 + method_c * 0.15
        method_str = "QPAREB comparable 45% + income (CMHC/cap) 40% + cost 15%"
    elif grp == "single_family" and method_b:
        # Single-family with 2 units (semi-duplex) — light income weight
        base = method_a * 0.60 + method_b * 0.25 + method_c * 0.15
        method_str = "QPAREB comparable 60% + income 25% + cost 15%"
    elif qpareb_type == "condo":
        base = method_a * 0.80 + method_c * 0.20
        method_str = "QPAREB comparable 80% + cost approach 20%"
    else:
        base = method_a * 0.65 + method_c * 0.35
        method_str = "QPAREB comparable 65% + cost approach 35%"

    # ── Market timing adjustment ──────────────────────────────────────────────
    # QPAREB medians are Q4 2025. Montreal prices up ~5.1% YoY (March 2026 WOWA/QPAREB).
    # We apply +2.5% to bring Q4 2025 medians to current (Apr 2026).
    base *= 1.025
    est  = round(base / 1000) * 1000

    # ── Uncertainty bands ─────────────────────────────────────────────────────
    # Borough-specific QPAREB median: ±15% (comparable sales spread is typically ±10-20%)
    # Island-wide fallback: ±25%
    unc = 0.15 if has_qpareb else 0.25

    # Build transparency detail
    parts = []
    if has_qpareb:
        parts.append(f"QPAREB/Centris Q4 2025 {qpareb_type} median for {b}: ${median_price:,} (size-adjusted ×{size_adj:.2f})")
    else:
        parts.append(f"No borough-specific QPAREB data — using island-wide median: ${median_price:,}")
    if method_b:
        parts.append(f"Income: {units} units × ${rent_mo}/mo CMHC 2024 rent × 12 × 0.65 NOI ÷ {cap}% cap = ${round(method_b/1000)*1000:,}")
    parts.append(f"Cost: {lot}m² lot + {bldg}m² building × {age_f:.0%} age factor")
    parts.append("Cross-reference with Evalweb (official assessed value) for your specific unit.")

    return {
        "estimated":             est,
        "low":                   round(est * (1-unc) / 1000) * 1000,
        "high":                  round(est * (1+unc) / 1000) * 1000,
        "method":                method_str,
        "cap_rate":              cap if method_b else None,
        "uncertainty":           f"±{int(unc*100)}%",
        "data_source":           f"QPAREB Q4 2025 ({qpareb_source})",
        "has_borough_data":      has_qpareb,
        "method_a_comparable":   round(method_a/1000)*1000,
        "method_b_income":       round(method_b/1000)*1000 if method_b else None,
        "method_c_cost":         round(method_c/1000)*1000,
        "qpareb_median":         median_price,
        "qpareb_type":           qpareb_type,
        "size_adj":              round(size_adj, 2),
        "age_factor":            age_f,
        "cmhc_rent_mo":          rent_mo if method_b else None,
        "sample_n":              0,
        "transaction_calibrated": has_qpareb,
        "note":                  " | ".join(parts),
    }

def permit_summary(conn, street_norm_val, borough=None, civic_start=None):
    """
    Count permits for this street, filtered by borough when possible.
    Uses exact street_norm match (not LIKE) to avoid over-counting.
    Borough filter prevents e.g. all 4,054 permits on "rue saint-hubert"
    island-wide being attributed to a single Plateau property.
    """
    if not street_norm_val: return {"total":0}
    c = conn.cursor()
    try:
        arrond_norm = norm(borough) if borough else None

        # Try: street + borough + tight civic range (address-level precision)
        if civic_start and arrond_norm:
            # First try exact address ±10 (catches multi-unit buildings with range entries)
            c.execute("""
                SELECT COUNT(*),
                  SUM(CASE WHEN UPPER(categorie) LIKE '%DEMOL%' THEN 1 ELSE 0 END),
                  SUM(CASE WHEN date_deliv>='2020' AND UPPER(nature_travaux||categorie) LIKE '%CONST%' THEN 1 ELSE 0 END)
                FROM permits
                WHERE street_norm=? AND norm_arrond=?
                  AND civic BETWEEN ? AND ?
            """, (street_norm_val, arrond_norm, civic_start-2, civic_start+10))
            row = c.fetchone()
            n = row[0] or 0
            if n > 0:
                return {"total":n,"demolitions":row[1]or 0,"recent_construction":row[2]or 0,"scope":"civic+borough"}

        # Try: street + borough (no civic filter)
        if arrond_norm:
            c.execute("""
                SELECT COUNT(*),
                  SUM(CASE WHEN UPPER(categorie) LIKE '%DEMOL%' THEN 1 ELSE 0 END),
                  SUM(CASE WHEN date_deliv>='2020' AND UPPER(nature_travaux||categorie) LIKE '%CONST%' THEN 1 ELSE 0 END)
                FROM permits
                WHERE street_norm=? AND (norm_arrond=? OR norm_arrond IS NULL OR norm_arrond='')
            """, (street_norm_val, arrond_norm))
            row = c.fetchone()
            n = row[0] or 0
            if n > 0:
                return {"total":n,"demolitions":row[1]or 0,"recent_construction":row[2]or 0,"scope":"borough"}

        # Fallback: street only
        c.execute("""
            SELECT COUNT(*),
              SUM(CASE WHEN UPPER(categorie) LIKE '%DEMOL%' THEN 1 ELSE 0 END),
              SUM(CASE WHEN date_deliv>='2020' AND UPPER(nature_travaux||categorie) LIKE '%CONST%' THEN 1 ELSE 0 END)
            FROM permits WHERE street_norm=?
        """, (street_norm_val,))
        row = c.fetchone()
        n = row[0] or 0
        return {"total":n,"demolitions":row[1]or 0,"recent_construction":row[2]or 0,"scope":"street"}
    except Exception:
        return {"total":0}

def enrich(r,ps,conn=None):
    borough=(r.get("borough") or "").strip()
    rem_name,rem_dist=get_rem(borough)

    # Geocode: try address geocache first (precise), fall back to borough centre
    prop_lat = r.get("lat") or None
    prop_lng = r.get("lng") or None
    geocoded = False
    if not prop_lat and GEOCACHE_LOADED:
        gc_lat, gc_lng = geocode_address(r.get("civic_start"), r.get("street"))
        if gc_lat:
            prop_lat, prop_lng = gc_lat, gc_lng
            geocoded = True
    if not prop_lat:
        bc = BOROUGH_CENTRES.get(norm_borough(borough),(None,None))
        prop_lat, prop_lng = bc

    metro_name, metro_dist, hfreq_bus_name, hfreq_bus_dist = nearest_stm(prop_lat, prop_lng)

    # Amenity proximity
    amenity = get_amenity_proximity(prop_lat, prop_lng)

    signals={
        "demolitionpermit":   (ps.get("demolitions") or 0)>0,
        "recentconstruction": (ps.get("recent_construction") or 0)>0,
        "highunits":          (r.get("nb_logements") or 0)>=4,
        "oldbuilding":        0<(r.get("year_built") or 9999)<1960,
        "largelot":           (r.get("lot_m2") or 0)>=300,
        "withinrem":          rem_dist is not None and rem_dist<=800,
        "multifloor":         (r.get("nb_etages") or 0)>=3,
        "permit_activity":    (ps.get("total") or 0)>=3,
        "nearmetro":          metro_dist is not None and metro_dist<=500,
        "frequenttransit":    hfreq_bus_dist is not None and hfreq_bus_dist<=300,
        "nearpark":           amenity.get("nearest_park_dist") is not None and amenity.get("nearest_park_dist",9999)<=300,
        "highcommercial":     amenity.get("commercial_500m",0)>=10,
        "highvacancy":        amenity.get("vacant_commercial_200m",0)>=3,
        "goodamenities":      amenity.get("facilities_1km",0)>=3,
    }
    return {
        "id":r["id"],"matricule":r.get("matricule"),
        "address":r.get("full_address"),"street":r.get("street"),
        "borough":borough,"use_type":r.get("cubf_label"),"cubf_code":r.get("cubf_code"),
        "year_built":r.get("year_built"),"nb_logements":r.get("nb_logements"),
        "nb_etages":r.get("nb_etages"),
        "superficie_terrain_m2":r.get("lot_m2"),"superficie_batiment_m2":r.get("bldg_m2"),
        "categorie":r.get("categorie"),"signals":signals,
        "permit_count":ps.get("total") or 0,
        "permit_scope":ps.get("scope","street"),
        # Coordinates
        "lat":prop_lat,"lng":prop_lng,"geocoded":geocoded,
        # Transit
        "nearest_rem":rem_name,"nearest_rem_dist_m":rem_dist,
        "within_800m_rem":rem_dist is not None and rem_dist<=800,
        "nearest_metro":metro_name,"nearest_metro_dist_m":metro_dist,
        "within_500m_metro":metro_dist is not None and metro_dist<=500,
        "nearest_hfreq_bus":hfreq_bus_name,"nearest_hfreq_bus_dist_m":hfreq_bus_dist,
        "within_300m_hfreq_bus":hfreq_bus_dist is not None and hfreq_bus_dist<=300,
        "stm_data_live":STM_LOADED,
        # Parks & green space
        "nearest_park":amenity.get("nearest_park"),
        "nearest_park_dist_m":amenity.get("nearest_park_dist"),
        "parks_500m":amenity.get("parks_500m",0),
        "parks_1km":amenity.get("parks_1km",0),
        # Public facilities
        "nearest_facility":amenity.get("nearest_facility"),
        "nearest_facility_dist_m":amenity.get("nearest_facility_dist"),
        "facilities_1km":amenity.get("facilities_1km",0),
        "nearest_library":amenity.get("nearest_library"),
        "nearest_library_dist_m":amenity.get("nearest_library_dist"),
        "nearest_pool":amenity.get("nearest_pool"),
        "nearest_pool_dist_m":amenity.get("nearest_pool_dist"),
        # POI
        "poi_500m":amenity.get("poi_500m",0),
        "cultural_poi_1km":amenity.get("cultural_poi_1km",0),
        "sport_poi_1km":amenity.get("sport_poi_1km",0),
        # Commercial
        "commercial_200m":amenity.get("commercial_200m",0),
        "commercial_500m":amenity.get("commercial_500m",0),
        "vacant_commercial_200m":amenity.get("vacant_commercial_200m",0),
        # Amenities loaded flag
        "amenities_live":AMENITIES_LOADED,
        "valuation":estimate_value(borough,r),
        "suite":r.get("suite",""),
    }

def search_properties(q, limit=10):
    """
    Search properties by address with multiple fallback strategies.

    The assessment roll has three address challenges:
    1. Many units (condos, apartments) have NO civic number — they share
       a building address. civic_start is NULL for these.
    2. NOM_RUE contains qualifiers: "avenue Atwater  (MTL+WMT)" —
       stripped by norm() so "atwater" matches.
    3. Street type prefix ("rue", "avenue") varies — user may omit it.

    Strategy cascade:
    A) civic + all words → exact civic range match
    B) civic + all words → civic ±10 (nearby units same building)
    C) civic + meaningful words (≥4 chars, skip "rue"/"avenue"/etc.)
    D) words only (no civic) → by relevance
    E) single longest word → broadest fallback
    """
    civic, street_raw = parse_address(q)
    sn = norm(street_raw)

    # Skip generic street-type words that appear in every street name
    SKIP = {"rue","avenue","boulevard","place","chemin","cote","montee","route",
            "rang","des","les","de","du","la","le","st","saint","sainte"}
    all_words   = [w for w in sn.split() if len(w) >= 2]
    good_words  = [w for w in sn.split() if len(w) >= 4 and w not in SKIP]
    key_words   = good_words or all_words  # fallback to all if no good words

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    rows = []

    def q_by_words(words, civic_clause="", extra_args=None):
        if not words: return []
        like = " AND ".join([f"street_norm LIKE ?"] * len(words))
        args = [f"%{w}%" for w in words]
        if extra_args: args += extra_args
        order = f"ABS(civic_start - {civic}) ASC, id ASC" if civic else "id ASC"
        sql = f"SELECT * FROM properties WHERE ({like}){civic_clause} ORDER BY {order} LIMIT {limit}"
        c.execute(sql, args)
        return [dict(r) for r in c.fetchall()]

    if all_words:
        if civic:
            # A: exact civic range match (civic_start <= searched <= civic_end)
            # COALESCE handles NULL civic_end (treat as single civic = civic_start)
            rows = q_by_words(all_words,
                f" AND civic_start IS NOT NULL AND civic_start <= {civic} AND COALESCE(civic_end, civic_start) >= {civic}")

            # B: ±2 (same or adjacent building — covers off-by-one in roll)
            if not rows:
                rows = q_by_words(key_words,
                    f" AND civic_start IS NOT NULL AND civic_start BETWEEN {max(0,civic-2)} AND {civic+2}")

            # C: ±50 (same block, any unit) — important because even civic numbers
            # are on one side of the street, odd on the other, and blocks are ~50 apart
            if not rows:
                rows = q_by_words(key_words,
                    f" AND civic_start IS NOT NULL AND civic_start BETWEEN {max(0,civic-50)} AND {civic+50}")

            # D: street only (catches condo units with NULL civic on same street)
            if not rows:
                rows = q_by_words(key_words)

        if not rows:
            # E: street words only, any civic
            rows = q_by_words(key_words)

        if not rows and good_words:
            # F: broadest fallback — single most distinctive word
            best = max(good_words, key=len)
            rows = q_by_words([best])

    results=[]
    for r in rows:
        sn_val=r.get("street_norm","")
        ps=permit_summary(conn, r.get("street_norm"), r.get("borough"), r.get("civic_start"))
        prop=enrich(r,ps,conn)

        # Individual permits
        if civic:
            c.execute("""SELECT no_permis,date_deliv,categorie,description,valeur FROM permits
                WHERE street_norm LIKE ? AND (civic IS NULL OR civic BETWEEN ? AND ?)
                ORDER BY date_deliv DESC LIMIT 5""",
                (f"%{sn_val}%",max(0,civic-5),civic+5))
        else:
            c.execute("""SELECT no_permis,date_deliv,categorie,description,valeur FROM permits
                WHERE street_norm LIKE ? ORDER BY date_deliv DESC LIMIT 8""",
                (f"%{sn_val}%",))
        prop["permits"]=[{"no":x[0],"date":x[1],"category":x[2],"description":x[3],"value":x[4]}
                         for x in c.fetchall()]
        results.append(prop)

    conn.close()
    return results

class Handler(BaseHTTPRequestHandler):
    def log_message(self,fmt,*args):
        print(f"  {fmt%args}")

    def send_json(self,data,status=200):
        body=json.dumps(data,ensure_ascii=False,default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type","application/json; charset=utf-8")
        self.send_header("Content-Length",len(body))
        self.send_header("Access-Control-Allow-Origin","*")
        self.send_header("Access-Control-Allow-Methods","GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers","Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin","*")
        self.send_header("Access-Control-Allow-Methods","GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers","Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed=urllib.parse.urlparse(self.path)
        p=urllib.parse.parse_qs(parsed.query)

        if parsed.path=="/health":
            try:
                conn=sqlite3.connect(DB_PATH); c=conn.cursor()
                c.execute("SELECT COUNT(*) FROM properties"); props=c.fetchone()[0]
                c.execute("SELECT COUNT(*) FROM permits"); perms=c.fetchone()[0]
                conn.close()
            except Exception: props=0; perms=0
            self.send_json({
                "status":"ok",
                "properties":props,
                "permits":perms,
                "contaminated":len(CONTAMINATED),
                "rem_stations":len(REM_STATIONS),
                "stm_stops":len(STM_STOPS),
                "parks":len(PARKS_STORE),
                "commercial":len(COMMERCIAL_STORE),
                "facilities":len(FACILITIES_STORE),
                "poi":len(POI_STORE),
                "geocache_streets":len(ADDR_GEOCACHE),
                "amenities_loaded":AMENITIES_LOADED,
                "stm_loaded":STM_LOADED,
                "market_rates_loaded":MARKET_RATES_LOADED,
                "transactions_loaded":TRANSACTIONS_LOADED,
                "facilities_loaded":len(FACILITIES_STORE),
                "parks_loaded":0,  # counted at runtime
            })

        elif parsed.path=="/stats":
            try:
                conn=sqlite3.connect(DB_PATH)
                c=conn.cursor()
                c.execute("SELECT COUNT(*) FROM properties"); props=c.fetchone()[0]
                c.execute("SELECT COUNT(*) FROM permits");   perms=c.fetchone()[0]
                conn.close()
                self.send_json({"properties":props,"permits":perms,
                                "contaminated_sites":len(CONTAMINATED),"rem_stations":len(REM_STATIONS)})
            except Exception as e: self.send_json({"error":str(e)},500)

        elif parsed.path=="/boroughs":
            try:
                conn=sqlite3.connect(DB_PATH)
                c=conn.cursor()
                c.execute("""SELECT borough, COUNT(*) FROM properties
                    WHERE borough IS NOT NULL AND borough!=''
                    GROUP BY borough ORDER BY 2 DESC""")
                boroughs=[row[0] for row in c.fetchall()]
                conn.close()
                self.send_json({"boroughs":boroughs})
            except Exception as e: self.send_json({"error":str(e)},500)

        elif parsed.path=="/search":
            q=p.get("q",[""])[0].strip()
            if not q: self.send_json({"error":"Missing ?q="},400); return
            try:
                results=search_properties(q)
                self.send_json({"query":q,"count":len(results),"results":results})
            except Exception as e:
                import traceback; traceback.print_exc()
                self.send_json({"error":str(e)},500)

        elif parsed.path=="/browse":
            try:
                borough   =p.get("borough",  [""])[0].strip()
                cubf      =p.get("cubf",     [""])[0].strip()
                units_min =int(p.get("units_min", ["1"])[0] or 1)
                floors_min=int(p.get("floors_min",["1"])[0] or 1)
                lot_min   =float(p.get("lot_min",  ["0"])[0] or 0)
                bldg_min  =float(p.get("bldg_min", ["0"])[0] or 0)
                year_min  =int(p.get("year_min", ["0"])[0] or 0)
                year_max  =int(p.get("year_max", ["9999"])[0] or 9999)
                page      =max(0,int(p.get("page",["0"])[0] or 0))
                page_size =min(100,max(10,int(p.get("page_size",["50"])[0] or 50)))
                sort      =p.get("sort",["id"])[0]

                wheres,args=[],[]
                if borough:     wheres.append("borough=?"); args.append(borough)
                if cubf=="residential":  wheres.append("cubf_code>=1000 AND cubf_code<1010")
                elif cubf=="income":     wheres.append("(nb_logements>=2 OR (cubf_code>=1010 AND cubf_code<2000))")
                elif cubf=="plex":       wheres.append("nb_logements>=4")
                elif cubf=="commercial": wheres.append("cubf_code>=2000 AND cubf_code<3000")
                if units_min>1:  wheres.append("nb_logements>=?"); args.append(units_min)
                if floors_min>1: wheres.append("nb_etages>=?");    args.append(floors_min)
                if lot_min>0:    wheres.append("lot_m2>=?");       args.append(lot_min)
                if bldg_min>0:   wheres.append("bldg_m2>=?");      args.append(bldg_min)
                if year_min>0:   wheres.append("year_built>=?");   args.append(year_min)
                if year_max<9999:wheres.append("year_built<=?");   args.append(year_max)

                wsql=("WHERE "+" AND ".join(wheres)) if wheres else ""
                SORT_MAP = {
                    # Opportunity / scoring — can only sort by stored fields;
                    # scoring is computed at enrich-time, so we approximate with
                    # permit count (activity proxy) and year (age proxy)
                    "score_desc":     "id ASC",           # default page order (scoring applied client-side on page)
                    "score_asc":      "id ASC",
                    "dist_desc":      "id ASC",
                    "dist_asc":       "id ASC",
                    "val_desc":       "id ASC",
                    "val_asc":        "id ASC",
                    "conf_desc":      "id ASC",
                    "conf_asc":       "id ASC",
                    # These can be done purely server-side
                    "units_desc":     "nb_logements DESC NULLS LAST",
                    "units_asc":      "nb_logements ASC NULLS LAST",
                    "lot_desc":       "lot_m2 DESC NULLS LAST",
                    "lot_asc":        "lot_m2 ASC NULLS LAST",
                    "bldg_desc":      "bldg_m2 DESC NULLS LAST",
                    "bldg_asc":       "bldg_m2 ASC NULLS LAST",
                    "year_asc":       "year_built ASC NULLS LAST",
                    "year_desc":      "year_built DESC NULLS LAST",
                    "permit_desc":    "id ASC",  # permit count computed at enrich time
                    "permit_asc":     "id ASC",
                    "val_price_desc": "lot_m2 DESC NULLS LAST",  # proxy: larger lot → higher value
                    "val_price_asc":  "lot_m2 ASC NULLS LAST",
                    "addr_asc":       "street ASC, civic_start ASC",
                    "addr_desc":      "street DESC, civic_start DESC",
                }
                osql = SORT_MAP.get(sort, "id ASC")

                conn=sqlite3.connect(DB_PATH)
                conn.row_factory=sqlite3.Row
                c=conn.cursor()
                c.execute(f"SELECT COUNT(*) FROM properties {wsql}",args)
                total=c.fetchone()[0]
                pages=max(1,(total+page_size-1)//page_size)
                c.execute(f"SELECT * FROM properties {wsql} ORDER BY {osql} LIMIT ? OFFSET ?",
                          args+[page_size,page*page_size])
                rows=[dict(r) for r in c.fetchall()]

                results=[]
                for r in rows:
                    sn=r.get("street_norm","")
                    ps=permit_summary(conn,sn,r.get("borough"),r.get("civic_start")) if sn else {}
                    results.append(enrich(r,ps,conn))
                conn.close()

                self.send_json({"total":total,"page":page,"page_size":page_size,
                                "pages":pages,"results":results})
            except Exception as e:
                import traceback; traceback.print_exc()
                self.send_json({"error":str(e)},500)


        elif parsed.path=="/amenities":
            self.send_json({
                "parks":len(PARKS_STORE),
                "facilities":len(FACILITIES_STORE),
                "poi":len(POI_STORE),
                "commercial":len(COMMERCIAL_STORE),
                "geocache_streets":len(ADDR_GEOCACHE),
                "amenities_loaded":AMENITIES_LOADED,
                "geocache_loaded":GEOCACHE_LOADED,
            })

        elif parsed.path=="/stm":
            # STM stop statistics and sample
            try:
                conn=sqlite3.connect(DB_PATH)
                c=conn.cursor()
                c.execute("SELECT COUNT(*) FROM stm_stops")
                total=c.fetchone()[0]
                c.execute("SELECT COUNT(*) FROM stm_stops WHERE is_metro=1")
                metro=c.fetchone()[0]
                c.execute("SELECT COUNT(*) FROM stm_stops WHERE is_highfreq=1 AND is_metro=0")
                hfreq=c.fetchone()[0]
                c.execute("SELECT * FROM stm_stops WHERE is_metro=1 ORDER BY trip_count DESC LIMIT 5")
                sample_metro=[dict(zip([d[0] for d in c.description],r)) for r in c.fetchall()]
                c.execute("SELECT * FROM stm_stops WHERE is_highfreq=1 AND is_metro=0 ORDER BY trip_count DESC LIMIT 5")
                sample_hfreq=[dict(zip([d[0] for d in c.description],r)) for r in c.fetchall()]
                conn.close()
                self.send_json({"total_stops":total,"metro_stops":metro,
                                "highfreq_bus_stops":hfreq,"stm_loaded":STM_LOADED,
                                "sample_metro":sample_metro,"sample_highfreq_bus":sample_hfreq})
            except Exception as e: self.send_json({"error":str(e)},500)

        elif parsed.path=="/market-rates":
            # Show derived market rates from transactions
            sample = {}
            if MARKET_RATES:
                for borough, rates in list(MARKET_RATES.get("by_borough",{}).items())[:8]:
                    sample[borough] = rates
            self.send_json({
                "loaded": MARKET_RATES_LOADED,
                "transactions_processed": TRANSACTIONS_LOADED,
                "boroughs_with_rates": len(MARKET_RATES.get("by_borough",{})),
                "island_wide": MARKET_RATES.get("island_wide",{}),
                "sample_borough_rates": sample,
            })

        elif parsed.path=="/debug-address":
            # Diagnose why a specific address is or isn't found
            # Usage: /debug-address?q=4266+rue+saint-hubert
            q = p.get("q", [""])[0].strip()
            if not q: self.send_json({"error": "Missing ?q="}, 400); return
            try:
                import urllib.parse as up
                civic, street_raw = parse_address(q)
                sn = norm(street_raw)
                SKIP = {"rue","avenue","boulevard","place","chemin","cote","montee","route",
                        "rang","des","les","de","du","la","le","st","saint","sainte"}
                key_words = [w for w in sn.split() if len(w) >= 4 and w not in SKIP] or sn.split()

                conn = sqlite3.connect(DB_PATH)
                conn.row_factory = sqlite3.Row
                c = conn.cursor()

                out = {"query": q, "parsed_civic": civic, "parsed_street": street_raw,
                       "normalized": sn, "key_words": key_words}

                # Exact civic
                c.execute("SELECT id,civic_start,civic_end,street,street_norm,borough,full_address FROM properties WHERE civic_start <= ? AND COALESCE(civic_end, civic_start) >= ? AND street_norm LIKE ?",
                    (civic, civic, f"%{key_words[0] if key_words else sn}%"))
                out["exact_civic"] = [dict(r) for r in c.fetchall()]

                # Civic range ±50
                if civic:
                    c.execute("SELECT id,civic_start,civic_end,street,street_norm,borough,full_address FROM properties WHERE street_norm LIKE ? AND civic_start BETWEEN ? AND ? ORDER BY civic_start",
                        (f"%{key_words[0] if key_words else sn}%", max(0,civic-50), civic+50))
                    out["range_50"] = [dict(r) for r in c.fetchall()]

                # Street only
                if key_words:
                    like = " AND ".join(["street_norm LIKE ?"] * len(key_words))
                    c.execute(f"SELECT COUNT(*) FROM properties WHERE {like}", [f"%{w}%" for w in key_words])
                    out["street_total"] = c.fetchone()[0]
                    c.execute(f"SELECT DISTINCT street, street_norm, borough FROM properties WHERE {like} LIMIT 5", [f"%{w}%" for w in key_words])
                    out["street_sample"] = [dict(r) for r in c.fetchall()]

                conn.close()
                self.send_json(out)
            except Exception as e:
                import traceback; traceback.print_exc()
                self.send_json({"error": str(e)}, 500)

        elif parsed.path=="/debug":
            out={}
            for key,src in SOURCES.items():
                path=src["path"]
                if path.exists():
                    try:
                        with open(path,encoding="utf-8",errors="replace") as f2:
                            line=f2.readline().strip()
                        sep=";" if line.count(";")>line.count(",") else ","
                        out[f"{key}_sep"]=sep
                        out[f"{key}_headers"]=line.split(sep)
                        with open(path,encoding="utf-8",errors="replace") as f2:
                            f2.readline()
                            out[f"{key}_row1"]=f2.readline().strip().split(sep)[:20]
                    except Exception as ex:
                        out[f"{key}_error"]=str(ex)
                else:
                    out[f"{key}_missing"]=True
            try:
                conn2=sqlite3.connect(DB_PATH)
                c2=conn2.cursor()
                c2.execute("SELECT borough,COUNT(*) FROM properties GROUP BY borough ORDER BY 2 DESC LIMIT 30")
                out["db_boroughs"]=[{"borough":r[0],"count":r[1]} for r in c2.fetchall()]
                c2.execute("PRAGMA table_info(properties)")
                out["db_columns"]=[r[1] for r in c2.fetchall()]
                c2.execute("SELECT * FROM properties LIMIT 3")
                cols=[d[0] for d in c2.description]
                out["db_sample"]=[dict(zip(cols,r)) for r in c2.fetchall()]
                conn2.close()
            except Exception as ex:
                out["db_error"]=str(ex)
            self.send_json(out)

        else:
            self.send_json({"error":"Not found"},404)

def main():
    global CONTAMINATED
    DATA_DIR.mkdir(exist_ok=True)
    print("\nMTL PropIntel — Backend Server v2")
    print("="*40)

    needs_rebuild=not DB_PATH.exists()
    if not needs_rebuild:
        try:
            conn=sqlite3.connect(DB_PATH)
            c=conn.cursor()
            c.execute("PRAGMA table_info(properties)")
            cols={row[1] for row in c.fetchall()}
            if "borough" not in cols or "street_norm" not in cols or "lot_m2" not in cols:
                print("  Old schema detected — rebuilding…")
                conn.close()
                DB_PATH.unlink()
                needs_rebuild=True
            else:
                c.execute("SELECT COUNT(*),COUNT(DISTINCT borough) FROM properties")
                row=c.fetchone()
                print(f"  Properties: {row[0]:,}  |  Boroughs: {row[1]}")
                # Borough quality check — if top borough is bare "Montreal" the
                # MUNICIPALITE code mapping failed; must rebuild to fix.
                c.execute("SELECT borough, COUNT(*) FROM properties WHERE borough!='' GROUP BY borough ORDER BY 2 DESC LIMIT 1")
                top = c.fetchone()
                if top and top[0] in ("Montreal","Ville de Montreal","montreal") and top[1] > 50000:
                    print(f"  ⚠  Borough data corrupt: {top[1]:,} properties mapped to '{top[0]}'.")
                    print(f"  ⚠  Auto-deleting and rebuilding database — please wait ~3 minutes…")
                    conn.close()
                    DB_PATH.unlink()
                    needs_rebuild = True
                else:
                    # Targeted fix for known borough misassignments without full rebuild
                    # RDP streets (high civic) sometimes get mapped to MHM via REM33
                    # Detect: streets in "MHM" with civic > 8500 are likely in RDP
                    c.execute("""
                        UPDATE properties SET borough='Riviere-des-Prairies-Pointe-aux-Trembles'
                        WHERE borough='Mercier-Hochelaga-Maisonneuve'
                          AND civic_start > 8500
                          AND (street_norm LIKE '%prairies%'
                               OR street_norm LIKE '%garneau%'
                               OR street_norm LIKE '%perras%'
                               OR street_norm LIKE '%marien%')
                    """)
                    fixed = conn.total_changes
                    if fixed > 0:
                        conn.commit()
                        print(f"  Fixed {fixed} RDP properties misassigned to MHM")
                    # Fix any street_norm values with leftover parenthetical qualifiers
                    c.execute("SELECT COUNT(*) FROM properties WHERE street_norm LIKE '%(%)%'")
                    qual_count=c.fetchone()[0]
                    if qual_count > 0:
                        print(f"  Fixing {qual_count:,} street_norm values with qualifiers…")
                        c.execute("SELECT id, street_norm FROM properties WHERE street_norm LIKE '%(%)%'")
                        stale = c.fetchall()
                        batch = [(re.sub(r"[\s\-]+"," ",re.sub(r"\s*\([^)]*\)","",sn or "").strip()).strip(), pid) for pid,sn in stale]
                        c.executemany("UPDATE properties SET street_norm=? WHERE id=?", batch)
                        conn.commit()
                        print(f"  Fixed {len(batch):,} street_norm values")
                    conn.close()
        except Exception:
            needs_rebuild=True

    if needs_rebuild:
        print("\nFirst run — downloading and indexing real Montreal data.")
        print("This takes ~2 minutes and uses ~200MB of disk space.\n")
        build_properties_db()

    # Permits
    try:
        conn=sqlite3.connect(DB_PATH)
        c=conn.cursor()
        c.execute("SELECT COUNT(*) FROM permits")
        pcount=c.fetchone()[0]
        conn.close()
        if pcount==0: raise Exception("empty")
        print(f"  Permits: {pcount:,}")
    except Exception:
        build_permits_db()

    # Backfill missing borough names using permits CSV street→borough mapping
    try:
        conn=sqlite3.connect(DB_PATH)
        c=conn.cursor()
        c.execute("SELECT COUNT(*) FROM properties WHERE borough IS NULL OR borough=''")
        empty_boroughs=c.fetchone()[0]
        conn.close()
        if empty_boroughs>0:
            print(f"  {empty_boroughs:,} properties missing borough name — backfilling from permits…")
            backfill_boroughs_from_permits()
    except Exception as e:
        print(f"  Borough backfill skipped: {e}")

    # ── Load fast local data first ───────────────────────────────────────────
    print("  Loading contaminated sites...")
    try:
        CONTAMINATED=load_contaminated()
        print(f"  Contaminated sites: {len(CONTAMINATED)}")
    except Exception as e:
        print(f"  Contaminated skipped: {e}")

    def _check_and_build(table, build_fn, load_fn, label):
        try:
            conn=sqlite3.connect(DB_PATH); c=conn.cursor()
            c.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table}'")
            exists=c.fetchone() is not None
            if exists:
                c.execute(f"SELECT COUNT(*) FROM {table}")
                exists=c.fetchone()[0]>0
            conn.close()
            if not exists: build_fn()
            load_fn()
        except Exception as e:
            print(f"  {label} error: {e}")

    # Force rebuild parks if it parsed 0 rows (wrong column names previously)
    try:
        conn_p=sqlite3.connect(DB_PATH); cp=conn_p.cursor()
        cp.execute("SELECT COUNT(*) FROM parks")
        parks_count=cp.fetchone()[0]; conn_p.close()
        if parks_count==0:
            print("  Parks table empty — rebuilding with CKAN API…")
            build_parks_db()
    except Exception: pass

    _check_and_build("parks",     build_parks_db,     load_parks,     "Parks")

    # Force rebuild commercial if it failed (wrong URL previously)
    try:
        conn_c=sqlite3.connect(DB_PATH); cc=conn_c.cursor()
        cc.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='commercial'")
        has_c=cc.fetchone() is not None
        if has_c:
            cc.execute("SELECT COUNT(*) FROM commercial")
            has_c=cc.fetchone()[0]>0
        conn_c.close()
        if not has_c: build_commercial_db()
        load_commercial()
    except Exception as e: print(f"  Commercial error: {e}")

    # STM
    try:
        conn=sqlite3.connect(DB_PATH); c=conn.cursor()
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='stm_stops'")
        has_stm=c.fetchone() is not None
        if has_stm:
            c.execute("SELECT COUNT(*) FROM stm_stops")
            has_stm=c.fetchone()[0]>0
            # Force rebuild if using old non-deduplicated data:
            # old builds had many entries per station (70+ metro "stops"),
            # new builds have one entry per station (68 metro stations)
            if has_stm:
                c.execute("SELECT COUNT(*) FROM stm_stops WHERE is_metro=1")
                metro_n = c.fetchone()[0]
                if metro_n > 80:  # old data — rebuild
                    print(f"  STM: found {metro_n} metro entries (non-deduped) — rebuilding…")
                    has_stm = False
        conn.close()
        if not has_stm: build_stm_db()
        load_stm_stops()
    except Exception as e:
        print(f"  STM skipped: {e}")

    global AMENITIES_LOADED
    AMENITIES_LOADED = len(PARKS_STORE)>0

    # ── Start HTTP server NOW (before network-dependent data loads) ───────────
    server=HTTPServer(("127.0.0.1",PORT),Handler)
    print(f"\n✓ Server ready at http://localhost:{PORT}")
    print(f"  Health: http://localhost:{PORT}/health")
    print(f"  Browse: http://localhost:{PORT}/browse?page=0")
    print("\n  Open in browser: http://localhost:3000/montreal-propintel.html")
    print("  CKAN data (facilities, POI, geocache) loads in background.")
    print("  Press Ctrl+C to stop.\n")

    # ── Load network-dependent data in background thread ─────────────────────
    import threading
    def _bg():
        # Transactions + market rates (most important for valuation quality)
        try:
            build_market_rates()
        except Exception as e:
            print(f"  [bg] Market rates: {e}")
            import traceback; traceback.print_exc()
        try: load_facilities_from_ckan()
        except Exception as e: print(f"  [bg] Facilities: {e}")
        try: load_poi_from_ckan()
        except Exception as e: print(f"  [bg] POI: {e}")
        try: build_geocache()
        except Exception as e: print(f"  [bg] Geocache: {e}")
        global AMENITIES_LOADED
        AMENITIES_LOADED = len(PARKS_STORE)>0 or len(FACILITIES_STORE)>0
        print("  [bg] Background data load complete.")
    threading.Thread(target=_bg, daemon=True).start()

    try: server.serve_forever()
    except KeyboardInterrupt: print("\nStopped.")

if __name__=="__main__":
    main()
