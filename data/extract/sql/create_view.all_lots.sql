-- Create view for all lots

-- New: create views for each arrondissement and then union them up
CREATE OR REPLACE VIEW lot_view AS
SELECT 
  *, 
  'Villeray-St-Michele-Parc-Extension' as ARRONDISSEMENT 
FROM villeray_lots 
  WHERE BASE_USAGE is not null

UNION

SELECT 
  *, 
  'Rosemont–La Petite-Patrie' as ARRONDISSEMENT 
FROM rpp_lots 
  WHERE BASE_USAGE is not null

UNION

SELECT 
  *, 
  'LaSalle' as ARRONDISSEMENT 
FROM lasalle_lots 
  WHERE BASE_USAGE is not null

-- Old way: this doesn't include any zoning
CREATE OR REPLACE VIEW lot_view AS
SELECT 
  im.id_provinc,
  lot.rl0103a as NUMERO_LOT,
  adres.rl0101a as ADRESSE_INFÉRIEUR,
  adres.rl0101c as ADDRESSE_SUPÉRIEUR,
  concat_ws(' ', adres.rl0101g, adres.rl0101h) as VOIE,  -- include the orientation
  -- (AREA_M2 * 3.2808)
  round_even((rl0308a  * 3.2808), 2) as AIRE_DETAGES_SQFT,
  -- VALEUR_IMMEUBLE / (AREA_F2 * NOMBRE_ETAGES)
  round_even((rl0404a / (rl0308a * 3.2808)), 2) as DOLLAR_PER_FOOT,
  rl0306a as NOMBRE_ETAGES,  
  rl0311a as NOMBRE_LOGEMENTS,
  rl0404a as VALEUR_IMMEUBLE,
  rl0402a as VALEUR_TERRAIN,
  rl0403a as VALEUR_BÂTIMENT,
  rl0309a as TYPE_BÂTIMENT,
  z.BASE_USAGE as BASE_USAGE,
  z.MAX_ETAGES as MAX_ETAGES,
  z.USAGE_AUT as USAGE_AUT,
  z.USAGE_EXC as USAGE_EXC,
  z.ZONING_PDF as ZONING_PDF,
  rf.geom as lot_geom
FROM caracteristiques_immeuble as im
JOIN lot_cadastre as lot 
  ON im.id_provinc = lot.id_provinc
JOIN adresses as adres
  ON lot.id_provinc = adres.id_provinc
JOIN role_foncier as rf
  ON rf.id_provinc = lot.id_provinc
LEFT OUTER JOIN zoning as z
  ON rf.id_provinc = z.id_provinc
WHERE rl0402a > 1 
  AND '%C3%'
  AND rl0404a < 30000000  --VALEUR_IMMEUBLE
--   AND AIRE_DETAGES_SQFT < 1000000 --AIRE_DETAGES_SQFT
  AND rl0303a = 0  --ignore agricultural land

