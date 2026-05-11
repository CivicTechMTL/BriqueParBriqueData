# MTL PropIntel

A property intelligence tool for the Montreal agglomeration. Pulls real data from open municipal sources and serves it through a local API to a browser interface. Built for systematic property screening — not a replacement for professional appraisal or due diligence.

---

## Setup

### Requirements

- Python 3.8+
- No pip dependencies — uses only the standard library

### First run

```bash
# Terminal 1 — backend API (port 8000)
python3 server.py

# Terminal 2 — frontend file server (port 3000)
python3 -m http.server 3000
```

Open: **http://localhost:3000/montreal-propintel.html**

> The HTML must be served over HTTP (not `file://`) due to browser CORS restrictions.

### First-run downloads (~15 minutes, ~600MB total)

On first start the server downloads and indexes everything automatically:

| File | Size | Time |
|---|---|---|
| Assessment roll CSV | ~72MB | ~2 min |
| Building permits CSV | ~50MB | ~1 min |
| adresses.geojson (geocoding) | ~134MB | ~5 min |
| espace_vert.json (parks) | ~28MB | ~1 min |
| STM GTFS feed (transit) | ~20MB | ~1 min |
| Commercial premises CSV | ~5MB | ~30s |
| Facilities CKAN (background) | ~2MB | ~30s |
| Transactions CSVs 2023-2024 | ~5MB | ~30s |

After the first run everything loads from local cache in under 10 seconds.

---

## What's in the database

**512,288 properties** — every taxable unit in the Montreal agglomeration from the 2026-2028 assessment roll, including all 19 arrondissements and 14 demerged municipalities (Westmount, Côte-Saint-Luc, Mont-Royal, etc.).

**42 boroughs/municipalities** correctly resolved from the `NOM_RUE` street qualifier field and REM codes.

---

## Data sources

| Source | Data | Coverage | Freshness |
|---|---|---|---|
| Rôle d'évaluation foncière 2026-2028 | Year built, floors, units, lot area, building area, CUBF code, matricule | All 512k properties | Triennial — market value reference: July 1, 2024 |
| adresses-ponctuelles GeoJSON | Geocoded lat/lng for civic addresses | ~500k addresses | Updated periodically |
| permis-construction CSV | 550,417 building permits with civic number, category, date | Ville de Montréal arrondissements only | Weekly |
| STM GTFS | 8,893 stops, 68 metro stations (deduplicated), 8,075 high-freq bus stops | Island-wide | Updated by STM |
| REM stations | 22 stations with coordinates | Island + South Shore | Static April 2026 |
| espace_vert.json | 9,289 parks with polygon centroids | Island-wide | Annual |
| lieux-batiments-vocation-publique | Public facilities: libraries, arenas, community centres | Ville de Montréal arrondissements only | Updated by city |
| locaux-commerciaux-2024 | 28,462 commercial premises | Ville de Montréal arrondissements only | 2024 survey |
| Transactions CSVs 2023-2024 | Real estate transaction amounts by arrondissement | Ville de Montréal | Annual |
| QPAREB/Centris Q4 2025 | Borough-level median sale prices by property type | Island-wide | Quarterly |
| CMHC Rental Market Report 2024 | Average rents by borough | Montreal CMA | Annual |

---

## Valuation methodology

Three methods blended by property type:

**Method A — QPAREB comparable median**
Borough × property-type median sale price from Centris Q4 2025, adjusted for property size relative to the borough typical. Age factor NOT applied (QPAREB medians already reflect what buyers pay for older buildings).

**Method B — Income capitalisation** (2+ unit properties only)
`NOI = units × CMHC average monthly rent × 12 × 0.65` ÷ QPAREB cap rate.

**Method C — Cost approach**
Implied land rate from QPAREB median + CMHC replacement cost ($3,500/m² new) × age depreciation factor.

**Blend weights:**
- Condo: 90% comparable + 10% cost
- Single-family: 65% comparable + 35% cost
- Plex (2–5 units): 45% comparable + 40% income + 15% cost
- Multi (6+ units): 20% comparable + 65% income + 15% cost

**Uncertainty:** ±15% with borough-specific QPAREB data, ±25% island-wide fallback.

This estimate is a screening tool only. Do not use it to make an offer. For any property under serious consideration: look up the official assessed value on Evalweb using the matricule, and obtain a JLR report for transaction history and distress signals.

---

## Permit matching

Three-tier cascade shown in the expanded property row:

1. **Civic ±10 + borough** — near address-level precision
2. **Borough + street** — all permits on that street in that arrondissement  
3. **Street only** — island-wide fallback (may include other boroughs)

Permit data covers Ville de Montréal arrondissements only.

---

## Known limitations

**Valuation**
- No per-property assessed value — look up on Evalweb using the matricule
- No transaction history linked to specific properties (requires JLR ~$300/month)
- Borough-level medians can't account for specific street, condition, floor, or renovations
- Condo unit area estimated from lot share and building dimensions — roll doesn't record individual unit areas

**Geocoding**
- ~85% of properties geocode to precise address coordinates
- ~15% fall back to borough centroid — all proximity data for these is approximate
- Properties using centroid coordinates are flagged with ⚠

**Distress signals**
- None available from open data
- Pre-exercise notices, tax arrears, succession transfers require Nominis or JLR

**Coverage gaps**
- Commercial premises, facilities, and permits only cover Ville de Montréal arrondissements
- Demerged municipalities (Westmount, Pointe-Claire, Côte-Saint-Luc, Mont-Royal, Kirkland, etc.) show blank for these fields — correct, not a bug

**Transit distances**
- Straight-line (haversine), not walking distance
- REM distances don't account for terrain — some stations are geographically close but practically inaccessible

---

## Files

```
montreal-propintel.html     Frontend browser interface
server.py                   Local backend API + data pipeline
README.md                   This file

propintel_data/             Created automatically on first run
  properties.db             SQLite: properties + permits + parks + STM
  uniteevaluationfonciere.csv
  permis-construction.csv
  adresses.geojson              Full geocoded address dataset (134MB)
  espace_vert.json              Parks GeoJSON
  gtfs_stm.zip                  STM transit feed
  geocache.json                 Built from adresses.geojson
  transactions_2023.csv
  transactions_2024.csv
  facilities_cache.json
  poi_cache.json
```

---

## Refreshing data

```bash
# Full rebuild (re-downloads everything):
rm -rf propintel_data/
python3 server.py

# Rebuild database only (keep downloaded files):
rm propintel_data/properties.db
python3 server.py

# Rebuild geocache only:
rm propintel_data/geocache.json
python3 server.py

# Refresh permits only:
rm propintel_data/permis-construction.csv
python3 server.py
```

---

## API

| Endpoint | Description |
|---|---|
| `GET /health` | Server status and data loaded flags |
| `GET /browse?page=N&borough=X&sort=Y` | Paginated property list |
| `GET /search?q=ADDRESS` | Address search |
| `GET /boroughs` | All boroughs |
| `GET /market-rates` | Transaction-derived market rates |
| `GET /debug-address?q=ADDRESS` | Geocache and DB match diagnostics |
| `GET /stm?lat=X&lng=Y` | Nearest STM stops |

---

## For investment use

Appropriate for:
- Filtering 512k properties by borough, type, year, unit count, lot size
- Checking transit proximity and park access quickly
- Getting order-of-magnitude valuations for screening
- Identifying permit activity at a specific address

For any property under serious consideration:
1. Look up the official assessed value on **Evalweb** (use the matricule)
2. Check the **Registre foncier** for last sale price and date
3. Obtain a **JLR report** for distress signals and full transaction history
4. Engage a licensed appraiser for formal valuation
