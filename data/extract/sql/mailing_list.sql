-- analysis: finding properties to contact

Copy (
SELECT
  -- ID, ADDRESS, etc
  NUMERO_LOT,
  concat_ws(' ', concat_ws('-', ADRESSE_INFÉRIEUR, ADDRESSE_SUPÉRIEUR), VOIE) as ADRESSE,
  ARRONDISSEMENT,

  -- VALEUR
  round_even(DOLLAR_PER_FOOT, 2) as DOLLAR_PER_FOOT,

  -- ZONAGE
  concat_ws(';', BASE_USAGE, USAGE_AUT, USAGE_EXC) as ZONAGE,
  
  -- ATTRIBUTE
  round_even(AIRE_DETAGES_SQFT, 1) as AIRE_DETAGES_SQFT,

  -- zonage precisé
  ZONING_PDF,
  
  -- geom
  lot_geom
FROM lot_view
WHERE 
  -- DOLLAR_PER_FOOT < 300 
  -- AND DOLLAR_PER_FOOT > 100
  -- AND AIRE_DETAGES_SQFT > 100

  -- EXCLUSIONS
  BASE_USAGE IS NOT NULL -- only where we have zoning
  
  -- ZONAGE 
  AND -- Commercial 3-10
    ZONAGE SIMILAR TO '.*(C\.([3-9]|10)).*'
  AND -- Exclude all residential
    ZONAGE NOT ILIKE '%H%'
ORDER BY
  DOLLAR_PER_FOOT asc
) TO 'cX-no-H.parquet' WITH (FORMAT parquet);