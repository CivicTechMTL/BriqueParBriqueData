-- Step 3: Load

-- For each layer desired create a table, example:
-- ['"rol_unite_p_2026"', '"b05v_unite_evaln_2026"', '"b05v_adr_unite_evaln_2026"', '"b05v_repar_fisc_2026"', '"b05v_lot_cadst_2026"']

-- CREATE TABLE lot_cadastre AS
SELECT * FROM ST_Read('role-fonciere/out/Role2026_geopackage/Role_2026_2.gpkg', layer = "b05v_lot_cadst_2026");

-- Load in Villeray zoning
CREATE TABLE villeray_zoning AS
SELECT * FROM ST_Read('zoning/out/villeray-zoning.geojson')

-- RPP zoning
CREATE TABLE rpp_zoning AS
SELECT * FROM ST_Read('zoning/rpp/Zones_RPP_4326.shp')

-- Ville Marie (currently missing dbf)
CREATE TABLE vm_usage AS
SELECT * FROM ST_Read('zoning/ville-marie/Usages_VM_region.shp') 

-- LaSalle
CREATE TABLE lasalle_zoning AS
SELECT * FROM ST_Read('zoning/lasalle/lasalle_zonage.json')