# Montreal Rôle Foncier data

## What

The [city of Montreal has a website](https://montreal.ca/role-evaluation-fonciere/adresse/liste/resultat) where one can look up fairly important details of any given property, searchable by address. This data is used by Brique par brique to evaluate potential opportunities for new commercial or residential space.

The part of the city responsible - [Direction de l'évaluation foncière](https://montreal.ca/lieux/direction-de-levaluation-fonciere-point-de-service) - for this system are in Parc Extension.

The raw data seems to be available in various formats on donnees.quebec.ca [here](https://www.donneesquebec.ca/recherche/dataset/roles-d-evaluation-fonciere-du-quebec/resource/8a79d011-0f0e-42fa-af68-049f741e8919)

## Data available

### Identification de l'unité d'évaluation
- Adresse
- Arrondissement
- Numéro de lot: XXXXXXX
- Numéro de matricule: XXXX-XX-XXXX-X-XXX-XXXX
- Utilisation prédominante: Logement, other
- Numéro d'unité de voisinage: XXXX
- Numéro de compte foncier: XX - XXXXXXXXX

### Propriétaire
- Nom
- Statut aux fins d'imposition scolaire: Personne physique, enterprise, etc
- Adresse postale
- Date d'inscription au rôle

### Caractéristiques de l'unité d'évaluation
#### Caractéristiques du terrain
##### Mesure frontale
- Superficie: in metres 

##### Caractéristiques du bâtiment principal
- Nombre d'étages
- Année de construction
- Aire d'étages
- Genre de construction
- Lien physique
- Nombre de logements
- Nombre de locaux non résidentiels
- Nombre de chambres locatives

### Valeurs au rôle d’évaluation
#### Rôle courant
- Date de référence au marché
- Valeur du terrain: $$$
- Valeur du bâtiment: $$$
- Valeur de l'immeuble: $$$

#### Rôle antérieur
- Date de référence au marché
- Valeur de l'immeuble au rôle antérieur

#### Répartition fiscale
- Valeur imposable de l'immeuble
- Valeur non imposable de l'immeuble

## How to obtain data

UX - standard flow

1. Look up by adresse

    `GET https://montreal.ca/role-evaluation-fonciere/adresse`

    Form:

    Put in adresse number
    Put in street 
    Submit

2. Results: list of addresses

    User selects correct address

    ```
    POST https://montreal.ca/role-evaluation-fonciere/adresse/liste

    body: "civicNumber=7655&streetNameCombobox=Rue+Berri%2C+Arrondissement+de+Villeray+-+Saint-Michel+-+Parc-Extension+%28Montr%C3%A9al%29&streetGeneric=Rue&streetName=BERRI&noCity=50&boroughNumber=25&streetNameOfficial=Berri&suiteNumber=&token=XXXXXXXXX"
    ```


    Example result:

        Adresse: 7655 - 7661 Rue Berri (Montréal)
        Numéro de compte foncier: 30 - F68381250
        Numéro de matricule: 9544-26-8614-3-000-0000

3. Click on result

    ```
    POST https://montreal.ca/role-evaluation-fonciere/adresse/liste/resultat
    body: "evalUnitId=3048236"
    ```

    Response: HTML (Example)

    ```html
    <ul data-test="list" class="empty-placeholder list">
    <li data-test="item" class="list-item">
        <div class="list-item-content">
            <div data-test="label" class="list-item-label">Nom</div>
            <div>TROMBLAY, JEAN</div>
        </div>
    </li>
    <li data-test="item" class="list-item">
        <div class="list-item-content">
            <div data-test="label" class="list-item-label">Statut aux fins d'imposition scolaire</div>
            <div>Personne physique</div>
        </div>
    </li>
    ```

---


Base URL for lookup by adresse
https://montreal.ca/role-evaluation-fonciere/adresse

https://montreal.ca/info-recherche/api/evaluation-fonciere/gem/streets?q=Rue+Berri%2C+Arrondissement+de+Villeray+-+Saint-Michel+-+Parc-Extension+%28Montr%C3%A9al%29&page=1&size=10





fetch("https://montreal.ca/role-evaluation-fonciere/adresse/liste/resultat", {
  "headers": {
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "accept-language": "en-US,en;q=0.9",
    "cache-control": "no-cache",
    "content-type": "application/x-www-form-urlencoded",
    "pragma": "no-cache",
    "priority": "u=0, i",
    "sec-ch-ua": "\"Not/A)Brand\";v=\"99\", \"Chromium\";v=\"148\"",
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": "\"macOS\"",
    "sec-fetch-dest": "document",
    "sec-fetch-mode": "navigate",
    "sec-fetch-site": "same-origin",
    "sec-fetch-user": "?1",
    "upgrade-insecure-requests": "1"
  },
  "referrer": "https://montreal.ca/role-evaluation-fonciere/adresse/liste",
  "body": "evalUnitId=3048236",
  "method": "POST",
  "mode": "cors",
  "credentials": "include"
}).then(r => console.log(r.body));