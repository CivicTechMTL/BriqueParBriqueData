# Montreal - Ma Carte Interactive

## What
This is the principal online map for the various buroughs (arrondisement) in Montreal. It can be found [here](https://spectrum.montreal.ca/).

## Data available

There are many layers, but availability is on a burough-by-burough basis. See [this issue](https://github.com/CivicTechMTL/BriqueParBriqueData/issues/4#issuecomment-4639451982) related to the availability of zoning for each city. Other relevant layers include the rôle foncier, which appear to be the cadestral information (property lines).

Example for Villeray-St-Michel-Parc-Extension: 

1. `Zone`: Zoning information
2. `Role Foncier`: This appears to be parcel/lot information, but it doesn't include a general lot number but rather a range of address numbers.


## Technologies used

The application uses [Spectrum Spatial Analyst](https://sgsi.com/spectrum-spatial-analyst/) a product of a small geospatial software company out of Washington State.



## How to obtain data

### Download tables

For some arrondisements some of the attribute data is available for extraction en masse. This does not contain spatial data.

Example steps:

1. `Map Project` (top right cornder) > `Villeray-St-Michel-Parc-Extension` 

2. `Règlements d'urbanisme` > `Zone` > (three dots) > `See Tabular Results`

3. `Zone in [All Data]` (left) > (three dots) > `Export all pages as CSV`

### Zone/parcel attributes

The application relies on a backend FeatureService can be [found here](https://spectrum.montreal.ca/connect/analyst/controller/connectProxy/rest/Spatial/FeatureService). This is how attributes are queried when one clicks on a particular location.

There doesn't appear to be a web interface for the server. An example request:

```bash
$ curl 'https://spectrum.montreal.ca/connect/analyst/controller/connectProxy/rest/Spatial/FeatureService' \
  -H 'accept: application/json, text/plain, */*' \
  -H 'accept-language: en-US,en;q=0.9' \
  -H 'cache-control: no-cache' \
  -H 'content-type: application/x-www-form-urlencoded; charset=UTF-8' \
  -b 'JSESSIONID=119E0B6BDC0D7A89FB33DE92E41634F1' \
  -H 'origin: https://spectrum.montreal.ca' \
  -H 'pragma: no-cache' \
  -H 'priority: u=1, i' \
  -H 'sec-ch-ua: "Not/A)Brand";v="99", "Chromium";v="148"' \
  -H 'sec-ch-ua-mobile: ?0' \
  -H 'sec-fetch-dest: empty' \
  -H 'sec-fetch-mode: cors' \
  -H 'sec-fetch-site: same-origin' \
  -H 'user-agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36' \
  --data-raw $'url=tables%2Ffeatures.json%3Fpage%3D1%26pageLength%3D50&encodeSpecialChars=true&postData=%7B%22query%22%3A%22SELECT%20%5C%22NUMERO_COMPLET%5C%22%2C%5C%22NUMERO%5C%22%2C%5C%22EN_MODIF%5C%22%2C%5C%22USAGE%5C%22%2C%5C%22USAGE_AUT%5C%22%2C%5C%22USAGE_EXC%5C%22%2C%5C%22ETAGE_MIN%5C%22%2C%5C%22ETAGE_MAX%5C%22%2C%5C%22METRE_MIN%5C%22%2C%5C%22METRE_MAX%5C%22%2C%5C%22TAUX_IMP_MIN%5C%22%2C%5C%22TAUX_IMP_MAX%5C%22%2C%5C%22COS_MIN%5C%22%2C%5C%22COS_MAX%5C%22%2C%5C%22IMPLANTATION%5C%22%2C%5C%22USAGE_DEBIT%5C%22%2C%5C%22USAGE_RESTO%5C%22%2C%5C%22RDC_COMMERCIAL%5C%22%2C%5C%22USAGE_CAFE_TERRASSE%5C%22%2C%5C%22CONT_DEBIT%5C%22%2C%5C%22CONT_RESTO%5C%22%2C%5C%22DISPOSITION%5C%22%2C%5C%22CONV_RDC_COM_A_LOG%5C%22%2C%5C%22CUVETTE%5C%22%2C%5C%22SECTEUR_PAT%5C%22%2C%5C%22SECTEUR_PIIA%5C%22%2C%5C%22CAT_AFFICHAGE%5C%22%2C%5C%22BAT_HAUTEUR_MOY%5C%22%2C%5C%22BAT_HAUTEUR_MIN%5C%22%2C%5C%22BAT_HAUTEUR_MAX%5C%22%2C%5C%22BAT_ETAGE_MOY%5C%22%2C%5C%22BAT_ETAGE_MIN%5C%22%2C%5C%22BAT_ETAGE_MAX%5C%22%2C%5C%22LIEN_GRILLE%5C%22%2C%5C%22MISE_A_JOUR%5C%22%2C%5C%22RAISON_MAJ%5C%22%2C%5C%22MODIF_NOTE%5C%22%2C%5C%22MODIF_LIEN%5C%22%20FROM%20%5C%22%2F19_VSMPE%2FReglement_urbanisme%2FVSP_REG_ZONE%5C%22%20WHERE%20MI_Intersects(obj%2CMI_Box(-8193872.676871861%2C5709650.947006683%2C-8193853.567614793%2C5709670.056263751%2C\'EPSG%3A3857\'))%22%7D&projectName=%2F-%20Villeray%E2%80%93Saint-Michel%E2%80%93Parc-Extension'
```

### Map tiles/images

All of the visible layers are produced by the [Mapserver](https://spectrum.montreal.ca/connect/analyst/controller/connectProxy/rest/Spatial/MappingService), which send out PNG images to overlay on the basemap. This is a pretty standard setup, though more modern solutions use vector tile maps.

Sample request:

```bash
$ curl 'https://spectrum.montreal.ca/connect/analyst/controller/connectProxy/rest/Spatial/MappingService' \
  -H 'accept: application/json, text/plain, */*' \
  -H 'accept-language: en-US,en;q=0.9' \
  -H 'cache-control: no-cache' \
  -H 'content-type: application/x-www-form-urlencoded; charset=UTF-8' \
  -b 'JSESSIONID=119E0B6BDC0D7A89FB33DE92E41634F1' \
  -H 'origin: https://spectrum.montreal.ca' \
  -H 'pragma: no-cache' \
  -H 'priority: u=1, i' \
  -H 'sec-ch-ua: "Not/A)Brand";v="99", "Chromium";v="148"' \
  -H 'sec-ch-ua-mobile: ?0' \
  -H 'sec-ch-ua-platform: "macOS"' \
  -H 'sec-fetch-dest: empty' \
  -H 'sec-fetch-mode: cors' \
  -H 'sec-fetch-site: same-origin' \
  -H 'user-agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36' \
  --data-raw $'url=maps%2Fimage.png%3Bw%3D542%3Bh%3D542%3Bz%3D1294.6521664001048%20m%3Bc%3D-8193437.934804077%2C5713209.241351928%2CEPSG%3A3857&postData=%7B%22layers%22%3A%5B%7B%22type%22%3A%22NamedLayer%22%2C%22name%22%3A%22%2F19_VSMPE%2FMairie%2FVSMPE_Mairie_Layers%2FMairie_%20%20405_%20avenue%20Ogilvy%22%7D%2C%7B%22type%22%3A%22NamedLayer%22%2C%22name%22%3A%22%2F19_VSMPE%2FMairie%2FVSMPE_Mairie_Layers%2FLimite%20d\'arrondissement%22%7D%2C%7B%22type%22%3A%22NamedLayer%22%2C%22name%22%3A%22%2F19_VSMPE%2FMairie%2FVSMPE_Mairie_Layers%2FArrondissements%20voisins%22%7D%5D%7D&projectName=%2F-%20Villeray%E2%80%93Saint-Michel%E2%80%93Parc-Extension'
```