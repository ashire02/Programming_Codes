// ============================================================
//  NDVI Analysis for Nepal using Landsat 8/9 OLI
//  Asset: projects/ashire02/assets/Nepal
//  Author: ashire02
//  Platform: Google Earth Engine (GEE)
// ============================================================

// ----------------------------------------------------------
// 1. LOAD AOI (Area of Interest)
// ----------------------------------------------------------
var nepal = ee.FeatureCollection('projects/ashire02/assets/Nepal');
var aoi   = nepal.geometry();

// ----------------------------------------------------------
// 2. DATE RANGE & CLOUD FILTER
//    Using a recent dry/growing season window.
//    Adjust start/end to your target season.
// ----------------------------------------------------------
var START_DATE  = '2023-10-01';
var END_DATE    = '2024-04-30';
var CLOUD_COVER = 20; // max % cloud cover per scene

// ----------------------------------------------------------
// 3. LOAD LANDSAT 8 & 9 SURFACE REFLECTANCE (Collection 2)
//    Landsat 9 launched 2021-09-27; combined with L8 for
//    maximum scene coverage over Nepal.
// ----------------------------------------------------------

// --- Masking function: cloud, cloud shadow, snow via QA_PIXEL ---
function maskL89sr(image) {
  var qaBand     = image.select('QA_PIXEL');
  // Bit 3 = cloud shadow, Bit 4 = snow, Bit 5 = cloud
  var cloudMask  = qaBand.bitwiseAnd(1 << 3).eq(0)
                         .and(qaBand.bitwiseAnd(1 << 4).eq(0))
                         .and(qaBand.bitwiseAnd(1 << 5).eq(0));
  // Scale reflectance bands: multiply by 0.0000275, add -0.2
  return image
    .updateMask(cloudMask)
    .select(['SR_B4', 'SR_B5'])
    .multiply(0.0000275).add(-0.2)
    .copyProperties(image, ['system:time_start']);
}

var l8 = ee.ImageCollection('LANDSAT/LC08/C02/T1_L2')
  .filterBounds(aoi)
  .filterDate(START_DATE, END_DATE)
  .filter(ee.Filter.lt('CLOUD_COVER', CLOUD_COVER))
  .map(maskL89sr);

var l9 = ee.ImageCollection('LANDSAT/LC09/C02/T1_L2')
  .filterBounds(aoi)
  .filterDate(START_DATE, END_DATE)
  .filter(ee.Filter.lt('CLOUD_COVER', CLOUD_COVER))
  .map(maskL89sr);

// Merge both sensors
var landsat = l8.merge(l9);
print('Total scenes used:', landsat.size());

// ----------------------------------------------------------
// 4. COMPUTE NDVI
//    NDVI = (NIR - Red) / (NIR + Red)
//    Landsat 8/9: SR_B5 = NIR, SR_B4 = Red
// ----------------------------------------------------------
function addNDVI(image) {
  var ndvi = image.normalizedDifference(['SR_B5', 'SR_B4'])
                  .rename('NDVI');
  return image.addBands(ndvi);
}

var ndviCollection = landsat.map(addNDVI);

// Median composite — robust to remaining outliers/shadows
var ndviMedian = ndviCollection
  .select('NDVI')
  .median()
  .clip(aoi);

// ----------------------------------------------------------
// 5. NDVI CLASSIFICATION
//    Standard 6-class land-cover/vegetation scheme:
//    < 0.0  → Water / Non-vegetated (bare rock, snow)
//    0.0–0.1 → Bare soil / Built-up / Sparse cover
//    0.1–0.2 → Very sparse vegetation / degraded land
//    0.2–0.4 → Moderate vegetation (shrubs, grassland)
//    0.4–0.6 → Dense vegetation (mixed forest, cropland)
//    > 0.6  → Very dense / healthy vegetation (dense forest)
// ----------------------------------------------------------
var classified = ndviMedian
  .where(ndviMedian.lt(0.0), 1)
  .where(ndviMedian.gte(0.0).and(ndviMedian.lt(0.1)), 2)
  .where(ndviMedian.gte(0.1).and(ndviMedian.lt(0.2)), 3)
  .where(ndviMedian.gte(0.2).and(ndviMedian.lt(0.4)), 4)
  .where(ndviMedian.gte(0.4).and(ndviMedian.lt(0.6)), 5)
  .where(ndviMedian.gte(0.6), 6)
  .rename('NDVI_Class');

// ----------------------------------------------------------
// 6. VISUALISATION PARAMETERS
// ----------------------------------------------------------

// Continuous NDVI gradient (standard RdYlGn palette)
var ndviVis = {
  min: -0.2,
  max:  0.8,
  palette: [
    '#d73027', // deep red  – water/non-veg
    '#fc8d59', // orange    – bare soil
    '#fee08b', // yellow    – sparse
    '#d9ef8b', // light green – moderate
    '#91cf60', // green       – dense
    '#1a9850'  // dark green  – very dense
  ]
};

// Classified discrete palette
var classVis = {
  min: 1,
  max: 6,
  palette: ['#4575b4', '#d73027', '#fdae61', '#fee08b', '#74c476', '#238b45']
};

// ----------------------------------------------------------
// 7. ADD LAYERS TO MAP
// ----------------------------------------------------------
Map.centerObject(aoi, 7);

// AOI boundary
Map.addLayer(nepal, {color: 'black'}, 'Nepal Boundary', true, 0.8);

// Continuous NDVI
Map.addLayer(ndviMedian, ndviVis, 'NDVI (Median Composite)', true);

// Classified NDVI
Map.addLayer(classified, classVis, 'NDVI Classification', false);

// ----------------------------------------------------------
// 8. LEGEND  (continuous + classified)
// ----------------------------------------------------------
var legend = ui.Panel({
  style: {position: 'bottom-left', padding: '8px 15px'}
});

legend.add(ui.Label({
  value: 'NDVI Classification',
  style: {fontWeight: 'bold', fontSize: '14px', margin: '0 0 6px 0'}
}));

var classLabels = [
  {color: '#4575b4', label: '< 0.0  — Water / Non-vegetated'},
  {color: '#d73027', label: '0.0–0.1 — Bare soil / Built-up'},
  {color: '#fdae61', label: '0.1–0.2 — Very sparse vegetation'},
  {color: '#fee08b', label: '0.2–0.4 — Moderate vegetation'},
  {color: '#74c476', label: '0.4–0.6 — Dense vegetation'},
  {color: '#238b45', label: '> 0.6  — Very dense / healthy forest'}
];

classLabels.forEach(function(item) {
  var row = ui.Panel({
    layout: ui.Panel.Layout.flow('horizontal'),
    style: {margin: '2px 0'}
  });
  row.add(ui.Label({
    style: {
      backgroundColor: item.color,
      padding: '8px',
      margin: '0 6px 0 0'
    }
  }));
  row.add(ui.Label({value: item.label, style: {fontSize: '11px'}}));
  legend.add(row);
});

Map.add(legend);

// ----------------------------------------------------------
// 9. STATISTICS — print zonal NDVI stats to console
// ----------------------------------------------------------
var stats = ndviMedian.reduceRegion({
  reducer: ee.Reducer.mean()
            .combine(ee.Reducer.min(),  '', true)
            .combine(ee.Reducer.max(),  '', true)
            .combine(ee.Reducer.stdDev(), '', true),
  geometry: aoi,
  scale:    30,
  maxPixels: 1e13,
  bestEffort: true
});

print('NDVI Statistics (mean | min | max | stdDev):', stats);

// ----------------------------------------------------------
// 10. EXPORT  — uncomment one block to export
// ----------------------------------------------------------

// --- Export continuous NDVI to Google Drive ---
// Export.image.toDrive({
//   image:       ndviMedian,
//   description: 'Nepal_NDVI_Landsat_Median',
//   folder:      'GEE_Exports',
//   fileNamePrefix: 'Nepal_NDVI',
//   region:      aoi,
//   scale:       30,
//   crs:         'EPSG:4326',
//   maxPixels:   1e13
// });

// --- Export classified NDVI to Google Drive ---
// Export.image.toDrive({
//   image:       classified,
//   description: 'Nepal_NDVI_Classified',
//   folder:      'GEE_Exports',
//   fileNamePrefix: 'Nepal_NDVI_Classified',
//   region:      aoi,
//   scale:       30,
//   crs:         'EPSG:4326',
//   maxPixels:   1e13
// });

// --- Export to GEE Asset ---
// Export.image.toAsset({
//   image:       ndviMedian,
//   description: 'Nepal_NDVI_Asset',
//   assetId:     'projects/ashire02/assets/Nepal_NDVI',
//   region:      aoi,
//   scale:       30,
//   maxPixels:   1e13
// });

// ============================================================
// END OF SCRIPT
// ============================================================
