# The city's online map will only return geojson by querying one
# feature at a time.

# https://spectrum.montreal.ca/

# This script iteratively downloads at ~630 features using the
# existing API, while limiting download speeds and having a
# wait time between requests to reduce server load.

# They have geojson files for each polygon (for some reason) 
# so we just increment and grab everything
# Example:
# wget http://www.example.com/index.php?file={1..500}


# Step 1: download
wget -P out --no-clobber --wait=2 --limit-rate=500k 
\ https://spectrum.montreal.ca/connect/analyst/controller/connectProxy/rest/Spatial/FeatureService?url=/tables/19_VSMPE/Reglement_urbanisme/VSP_REG_ZONE/features.json/
\ {1..634}?destinationSrs=epsg:3857&timestamp=1781541122002&projectName=/-%20Villeray%E2%80%93Saint-Michel%E2%80%93Parc-Extension
# ^ incrementing bit, thank you bash


# Step 2: set file name extension to geojson

for f in out/*; do mv -- "$f" "${f%}.json"; done

# Finally, merging all of the geojson files together can be 
# done with various tools - PROJ, GDAL, https://geoutil.com etc