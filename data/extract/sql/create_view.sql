-- Step 4: Query, create views

-- The process is 
-- 1. Load raw data from source as NAME_zoning
-- 2. Spatial join NAME_zoning with lots to create a view (below)
-- 3. Union the zoning views


-- Example: Villeray-St-Michel-ParcEx
CREATE OR REPLACE VIEW villeray_lots AS
SELECT 
  im.id_provinc,
  lot.rl0103a as NUMERO_LOT,
  adres.rl0101a as ADRESSE_INFÉRIEUR,
  adres.rl0101c as ADDRESSE_SUPÉRIEUR,
  concat_ws(' ', adres.rl0101g, adres.rl0101h) as VOIE,  -- include the orientation
  -- (AREA_M2 * 3.2808 * NOMBRE_ETAGES)
  round_even((rl0308a  * 3.2808), 2) as AIRE_DETAGES_SQFT,
  -- VALEUR_IMMEUBLE / (AREA_F2 * NOMBRE_ETAGES)
  round_even((rl0404a / (rl0308a * 3.2808)), 2) as DOLLAR_PER_FOOT,
  v_zoning.USAGE as BASE_USAGE,
  rl0306a as NOMBRE_ETAGES,
  v_zoning.ETAGE_MAX as MAX_ETAGES,
  rl0311a as NOMBRE_LOGEMENTS,
  rl0404a as VALEUR_IMMEUBLE,
  rl0402a as VALEUR_TERRAIN,
  rl0403a as VALEUR_BÂTIMENT,
  rl0309a as TYPE_BÂTIMENT,
  v_zoning.USAGE_AUT as USAGE_AUT,
  v_zoning.USAGE_EXC as USAGE_EXC,
  v_zoning.LIEN_GRILLE as ZONING_PDF,
  ST_Transform(rf.geom, 'EPSG:4269', 'EPSG:4326') as lot_geom
FROM caracteristiques_immeuble as im
JOIN lot_cadastre as lot 
  ON im.id_provinc = lot.id_provinc
JOIN adresses as adres
  ON lot.id_provinc = adres.id_provinc
JOIN role_foncier as rf
  ON rf.id_provinc = lot.id_provinc
OUTER JOIN villeray_zoning as v_zoning
  ON ST_Intersects(ST_SetCRS(rf.geom, 'EPSG:4326'), v_zoning.geom)
WHERE rl0402a > 1 
  -- AND DOLLAR_PER_FOOT < 800
  AND VALEUR_IMMEUBLE < 30000000
  AND AIRE_DETAGES_SQFT < 1000000
  AND rl0303a = 0  --ignore agricultural land


-- Example: LaSalle
-- Mostly the same as above, but zone code translation necessary
-- LeSalle view consistent with lot_view
CREATE OR REPLACE VIEW lasalle_lots AS
SELECT 
  im.id_provinc,
  lot.rl0103a as NUMERO_LOT,
  adres.rl0101a as ADRESSE_INFÉRIEUR,
  adres.rl0101c as ADDRESSE_SUPÉRIEUR,
  concat_ws(' ', adres.rl0101g, adres.rl0101h) as VOIE,  -- include the orientation
  -- (AREA_M2 * 3.2808 * NOMBRE_ETAGES)
  round_even((rl0308a  * 3.2808), 2) as AIRE_DETAGES_SQFT,
  -- VALEUR_IMMEUBLE / (AREA_F2 * NOMBRE_ETAGES)
  round_even((rl0404a / (rl0308a * 3.2808)), 2) as DOLLAR_PER_FOOT,
  
  -- c1c3c5 -> C.1;C.3;C.5
  array_to_string(list_transform(regexp_extract_all(lz.Classe, '(\D\d)'), lambda x : format('{}.{}', upper(x[1]), x[2])), ';') as BASE_USAGE,
  NULL as MAX_ETAGES,
  rl0306a as NOMBRE_ETAGES,
  rl0311a as NOMBRE_LOGEMENTS,
  rl0404a as VALEUR_IMMEUBLE,
  rl0402a as VALEUR_TERRAIN,
  rl0403a as VALEUR_BÂTIMENT,
  rl0309a as TYPE_BÂTIMENT,
  NULL as USAGE_AUT,
  NULL as USAGE_EXC,
  lz.Lien_complet_ftp as ZONING_PDF,
  ST_Transform(rf.geom, 'EPSG:4269', 'EPSG:4326') as lot_geom
FROM caracteristiques_immeuble as im
JOIN lot_cadastre as lot 
  ON im.id_provinc = lot.id_provinc
JOIN adresses as adres
  ON lot.id_provinc = adres.id_provinc
JOIN role_foncier as rf
  ON rf.id_provinc = lot.id_provinc
RIGHT OUTER JOIN lasalle_zoning as lz
  ON ST_Intersects(ST_SetCRS(rf.geom, 'EPSG:4326'), ST_SetCRS(lz.geom, 'EPSG:4326'))
WHERE rl0402a > 1 
  -- AND DOLLAR_PER_FOOT < 800
  AND VALEUR_IMMEUBLE < 30000000
  AND AIRE_DETAGES_SQFT < 1000000
  AND rl0303a = 0  --ignore agricultural land