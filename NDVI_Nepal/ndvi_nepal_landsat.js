// ================================================================
//  NDVI Analysis — Nepal  |  Landsat 5 / 8 / 9
//  Year-by-year navigation  |  1990 – 2025
//  Asset: projects/ashire02/assets/Nepal
// ================================================================
//
//  Sensor availability
//  Landsat 5  LANDSAT/LT05/C02/T1_L2   Red=SR_B3  NIR=SR_B4   1984 – May 2013
//  Landsat 8  LANDSAT/LC08/C02/T1_L2   Red=SR_B4  NIR=SR_B5   Apr 2013 – present
//  Landsat 9  LANDSAT/LC09/C02/T1_L2   Red=SR_B4  NIR=SR_B5   Oct 2022 – present (1 yr after launch)
// ================================================================

var L5_END   = '2013-05-05';
var L8_START = '2013-04-11';
var L9_START = '2022-10-01';

var SEASONS = {
  'Annual (Jan–Dec)'       : {s: '01-01', e: '12-31'},
  'Dry / Winter (Oct–Apr)' : {s: '10-01', e: '04-30'},
  'Pre-Monsoon (Mar–May)'  : {s: '03-01', e: '05-31'},
  'Monsoon (Jun–Sep)'      : {s: '06-01', e: '09-30'},
  'Post-Monsoon (Oct–Nov)' : {s: '10-01', e: '11-30'}
};

var CLASS_COLORS  = ['#4575b4','#d73027','#fdae61','#fee08b','#74c476','#238b45'];
var CLASS_LABELS  = [
  '< 0.0   Water / Snow',
  '0.0–0.1  Bare soil / Built-up',
  '0.1–0.2  Very sparse vegetation',
  '0.2–0.4  Moderate vegetation',
  '0.4–0.6  Dense vegetation',
  '> 0.6   Very dense / Healthy forest'
];

// ================================================================
//  AOI
// ================================================================
var nepal = ee.FeatureCollection('projects/ashire02/assets/Nepal');
var aoi   = nepal.geometry();

// ================================================================
//  LAYOUT
// ================================================================
ui.root.clear();

var map = ui.Map();
map.setOptions('HYBRID');
map.centerObject(aoi, 7);
map.addLayer(nepal, {color: '000000', fillColor: '00000000'}, 'Nepal Boundary');

var panel = ui.Panel({
  layout: ui.Panel.Layout.flow('vertical'),
  style : {width: '260px', padding: '10px'}
});

var split = ui.SplitPanel({
  firstPanel : panel,
  secondPanel: map,
  orientation: 'horizontal',
  wipe       : false
});
ui.root.add(split);

// ================================================================
//  WIDGETS  (plain GEE default look)
// ================================================================

panel.add(ui.Label('NDVI Analysis — Nepal', {fontWeight: 'bold', fontSize: '16px'}));
panel.add(ui.Label('Landsat 5 / 8 / 9  |  1990–2025', {fontSize: '11px', color: 'grey'}));
panel.add(ui.Label('────────────────────', {color: '#cccccc'}));

// ── Year selector + Prev / Next ──────────────────────────────────
panel.add(ui.Label('Year', {fontWeight: 'bold'}));

var MIN_YEAR = 1990;
var MAX_YEAR = 2025;
var yearSlider = ui.Slider({
  min: MIN_YEAR, max: MAX_YEAR, value: 2020, step: 1,
  style: {stretch: 'horizontal'}
});
var yearDisplay = ui.Label('2020', {fontWeight: 'bold', fontSize: '14px'});
yearSlider.onSlide(function(v) { yearDisplay.setValue(String(Math.round(v))); });

var prevBtn = ui.Button({label: '◀ Prev', style: {stretch: 'horizontal'}});
var nextBtn = ui.Button({label: 'Next ▶', style: {stretch: 'horizontal'}});

prevBtn.onClick(function() {
  var v = Math.max(MIN_YEAR, Math.round(yearSlider.getValue()) - 1);
  yearSlider.setValue(v);
  yearDisplay.setValue(String(v));
});
nextBtn.onClick(function() {
  var v = Math.min(MAX_YEAR, Math.round(yearSlider.getValue()) + 1);
  yearSlider.setValue(v);
  yearDisplay.setValue(String(v));
});

panel.add(ui.Panel(
  [prevBtn, yearDisplay, nextBtn],
  ui.Panel.Layout.flow('horizontal'),
  {stretch: 'horizontal'}
));
panel.add(yearSlider);

panel.add(ui.Label('────────────────────', {color: '#cccccc'}));

// ── Season ───────────────────────────────────────────────────────
panel.add(ui.Label('Season', {fontWeight: 'bold'}));
var seasonSel = ui.Select({
  items : Object.keys(SEASONS),
  value : 'Annual (Jan–Dec)',
  style : {stretch: 'horizontal'}
});
panel.add(seasonSel);

// ── Cloud cover ──────────────────────────────────────────────────
panel.add(ui.Label('Max Cloud Cover (%)', {fontWeight: 'bold'}));
var cloudSlider = ui.Slider({min: 5, max: 80, value: 20, step: 5, style: {stretch: 'horizontal'}});
var cloudDisplay = ui.Label('20%', {color: 'grey', fontSize: '11px'});
cloudSlider.onSlide(function(v) { cloudDisplay.setValue(String(Math.round(v)) + '%'); });
panel.add(cloudSlider);
panel.add(cloudDisplay);

// ── Composite method ─────────────────────────────────────────────
panel.add(ui.Label('Composite Method', {fontWeight: 'bold'}));
var methodSel = ui.Select({
  items : ['Median', 'Mean', 'Max (Greenest pixel)'],
  value : 'Median',
  style : {stretch: 'horizontal'}
});
panel.add(methodSel);

// ── Display layer ─────────────────────────────────────────────────
panel.add(ui.Label('Display Layer', {fontWeight: 'bold'}));
var displaySel = ui.Select({
  items : ['Continuous NDVI', 'Classified NDVI', 'Both'],
  value : 'Both',
  style : {stretch: 'horizontal'}
});
panel.add(displaySel);

panel.add(ui.Label('────────────────────', {color: '#cccccc'}));

// ── Run button ────────────────────────────────────────────────────
var runBtn = ui.Button({label: '▶  Run', style: {stretch: 'horizontal'}});
panel.add(runBtn);

var statusLbl = ui.Label('', {color: 'grey', fontSize: '11px'});
panel.add(statusLbl);

panel.add(ui.Label('────────────────────', {color: '#cccccc'}));

// ── Active sensors display ────────────────────────────────────────
panel.add(ui.Label('Active Sensor(s)', {fontWeight: 'bold'}));
var sensorPanel = ui.Panel();
sensorPanel.add(ui.Label('—', {color: 'grey', fontSize: '11px'}));
panel.add(sensorPanel);

panel.add(ui.Label('────────────────────', {color: '#cccccc'}));

// ── Statistics ────────────────────────────────────────────────────
panel.add(ui.Label('NDVI Statistics', {fontWeight: 'bold'}));
var statsPanel = ui.Panel();
statsPanel.add(ui.Label('Run to compute.', {color: 'grey', fontSize: '11px'}));
panel.add(statsPanel);

panel.add(ui.Label('────────────────────', {color: '#cccccc'}));

// ── Legend ────────────────────────────────────────────────────────
panel.add(ui.Label('Legend (Classified)', {fontWeight: 'bold'}));
CLASS_LABELS.forEach(function(lbl, i) {
  panel.add(ui.Panel(
    [
      ui.Label('', {backgroundColor: CLASS_COLORS[i], padding: '6px 10px', margin: '1px 5px 1px 0'}),
      ui.Label(lbl, {fontSize: '10px', margin: '4px 0'})
    ],
    ui.Panel.Layout.flow('horizontal')
  ));
});

panel.add(ui.Label('────────────────────', {color: '#cccccc'}));

// ── Export ────────────────────────────────────────────────────────
panel.add(ui.Label('Export to Drive', {fontWeight: 'bold'}));
var exportSel = ui.Select({
  items : ['Continuous NDVI', 'Classified NDVI'],
  value : 'Continuous NDVI',
  style : {stretch: 'horizontal'}
});
panel.add(exportSel);
var exportBtn = ui.Button({label: '⬇  Export', style: {stretch: 'horizontal'}});
panel.add(exportBtn);
var exportLbl = ui.Label('', {color: 'grey', fontSize: '11px'});
panel.add(exportLbl);

// ================================================================
//  PROCESSING FUNCTIONS
// ================================================================

function maskL5(image) {
  var qa   = image.select('QA_PIXEL');
  var mask = qa.bitwiseAnd(1 << 3).eq(0)
               .and(qa.bitwiseAnd(1 << 4).eq(0))
               .and(qa.bitwiseAnd(1 << 5).eq(0));
  return image.updateMask(mask)
    .select(['SR_B3', 'SR_B4']).multiply(0.0000275).add(-0.2)
    .rename(['Red', 'NIR'])
    .copyProperties(image, ['system:time_start']);
}

function maskL89(image) {
  var qa   = image.select('QA_PIXEL');
  var mask = qa.bitwiseAnd(1 << 3).eq(0)
               .and(qa.bitwiseAnd(1 << 4).eq(0))
               .and(qa.bitwiseAnd(1 << 5).eq(0));
  return image.updateMask(mask)
    .select(['SR_B4', 'SR_B5']).multiply(0.0000275).add(-0.2)
    .rename(['Red', 'NIR'])
    .copyProperties(image, ['system:time_start']);
}

function ndvi(image) {
  return image.normalizedDifference(['NIR', 'Red']).rename('NDVI')
    .copyProperties(image, ['system:time_start']);
}

function classifyNDVI(img) {
  return img.where(img.lt(0.0), 1)
            .where(img.gte(0.0).and(img.lt(0.1)), 2)
            .where(img.gte(0.1).and(img.lt(0.2)), 3)
            .where(img.gte(0.2).and(img.lt(0.4)), 4)
            .where(img.gte(0.4).and(img.lt(0.6)), 5)
            .where(img.gte(0.6), 6)
            .rename('NDVI_Class');
}

// Build date range for one year, handling cross-year seasons
function yearDateFilter(year, seasonKey) {
  var s = SEASONS[seasonKey];
  if (s.s <= s.e) {
    // Within same year
    return ee.Filter.date(year + '-' + s.s, year + '-' + s.e);
  } else {
    // Spans year boundary: e.g. Oct 2020 – Apr 2021
    return ee.Filter.or(
      ee.Filter.date(year       + '-' + s.s, year       + '-12-31'),
      ee.Filter.date((year + 1) + '-01-01',  (year + 1) + '-' + s.e)
    );
  }
}

// ================================================================
//  STATE
// ================================================================
var currentNDVI       = null;
var currentClassified = null;
var currentYear       = null;
var currentSeason     = null;

// ================================================================
//  RUN
// ================================================================
runBtn.onClick(function() {

  var year      = Math.round(yearSlider.getValue());
  var seasonKey = seasonSel.getValue();
  var cloud     = cloudSlider.getValue();
  var method    = methodSel.getValue();
  var display   = displaySel.getValue();

  statusLbl.setValue('Building collection for ' + year + '…');
  sensorPanel.clear();
  statsPanel.clear();
  statsPanel.add(ui.Label('Computing…', {color: 'grey', fontSize: '11px'}));

  // Which sensors are valid for this year?
  var useL5 = (year <= 2013);
  var useL8 = (year >= 2013);
  var useL9 = (year >= 2022);

  // Update sensor display
  var sensorLines = [];
  if (useL5) sensorLines.push('Landsat 5');
  if (useL8) sensorLines.push('Landsat 8');
  if (useL9) sensorLines.push('Landsat 9');
  sensorPanel.add(ui.Label(sensorLines.join(' + '), {fontSize: '12px'}));

  var dateFilter = yearDateFilter(year, seasonKey);
  var cols = [];

  if (useL5) {
    cols.push(
      ee.ImageCollection('LANDSAT/LT05/C02/T1_L2')
        .filterBounds(aoi)
        .filter(dateFilter)
        .filter(ee.Filter.date('1984-03-01', L5_END))
        .filter(ee.Filter.lt('CLOUD_COVER', cloud))
        .map(maskL5).map(ndvi)
    );
  }
  if (useL8) {
    cols.push(
      ee.ImageCollection('LANDSAT/LC08/C02/T1_L2')
        .filterBounds(aoi)
        .filter(dateFilter)
        .filter(ee.Filter.date(L8_START, '2025-12-31'))
        .filter(ee.Filter.lt('CLOUD_COVER', cloud))
        .map(maskL89).map(ndvi)
    );
  }
  if (useL9) {
    cols.push(
      ee.ImageCollection('LANDSAT/LC09/C02/T1_L2')
        .filterBounds(aoi)
        .filter(dateFilter)
        .filter(ee.Filter.date(L9_START, '2025-12-31'))
        .filter(ee.Filter.lt('CLOUD_COVER', cloud))
        .map(maskL89).map(ndvi)
    );
  }

  var merged = cols[0];
  for (var i = 1; i < cols.length; i++) merged = merged.merge(cols[i]);

  var composite;
  if      (method === 'Mean')                 composite = merged.mean();
  else if (method === 'Max (Greenest pixel)') composite = merged.max();
  else                                        composite = merged.median();

  var ndviImg  = composite.clip(aoi).rename('NDVI');
  var clsImg   = classifyNDVI(ndviImg);

  currentNDVI       = ndviImg;
  currentClassified = clsImg;
  currentYear       = year;
  currentSeason     = seasonKey;

  var ndviVis = {
    min: -0.2, max: 0.8,
    palette: ['#d73027','#fc8d59','#fee08b','#d9ef8b','#91cf60','#1a9850']
  };
  var clsVis = {min: 1, max: 6, palette: CLASS_COLORS};

  map.layers().reset();
  map.addLayer(nepal, {color: '000000', fillColor: '00000000'}, 'Nepal Boundary');

  if (display === 'Continuous NDVI' || display === 'Both')
    map.addLayer(ndviImg, ndviVis, 'NDVI ' + year + ' (Continuous)');
  if (display === 'Classified NDVI' || display === 'Both')
    map.addLayer(clsImg,  clsVis,  'NDVI ' + year + ' (Classified)');

  statusLbl.setValue('Map updated — ' + year);

  // Async stats — won't block UI
  ndviImg.reduceRegion({
    reducer   : ee.Reducer.mean()
                  .combine(ee.Reducer.min(),    '', true)
                  .combine(ee.Reducer.max(),    '', true)
                  .combine(ee.Reducer.stdDev(), '', true),
    geometry  : aoi,
    scale     : 500,
    maxPixels : 1e11,
    bestEffort: true
  }).evaluate(function(r, err) {
    statsPanel.clear();
    if (err || !r) {
      statsPanel.add(ui.Label('Stats unavailable.', {color: 'grey', fontSize: '11px'}));
      return;
    }
    var f = function(v) { return (v !== undefined && v !== null) ? v.toFixed(4) : 'N/A'; };
    [
      'Mean   : ' + f(r.NDVI_mean),
      'Min    : ' + f(r.NDVI_min),
      'Max    : ' + f(r.NDVI_max),
      'StdDev : ' + f(r.NDVI_stdDev)
    ].forEach(function(line) {
      statsPanel.add(ui.Label(line, {fontSize: '11px', fontFamily: 'monospace'}));
    });
  });

  // Scene count
  merged.size().evaluate(function(n, err) {
    if (!err && n !== null)
      statusLbl.setValue('Done — ' + year + '  |  ' + n + ' scenes');
  });
});

// ================================================================
//  EXPORT
// ================================================================
exportBtn.onClick(function() {
  if (!currentNDVI) { exportLbl.setValue('Run first.'); return; }
  var choice = exportSel.getValue();
  var tag    = (choice === 'Classified NDVI') ? 'Classified' : 'Continuous';
  var desc   = 'Nepal_NDVI_' + tag + '_' + currentYear + '_' +
               currentSeason.replace(/[^a-zA-Z0-9]/g, '_');

  var img;
  if (choice === 'Classified NDVI') {
    // Export as RGB — colors are baked in, opens correctly in QGIS/ArcGIS without any extra steps
    img = currentClassified.visualize({min: 1, max: 6, palette: CLASS_COLORS});
  } else {
    img = currentNDVI;
  }

  Export.image.toDrive({
    image         : img,
    description   : desc,
    folder        : 'GEE_Exports',
    fileNamePrefix: desc,
    region        : aoi,
    scale         : 30,
    crs           : 'EPSG:4326',
    maxPixels     : 1e13
  });
  exportLbl.setValue('Submitted. Check Tasks tab.');
});

// ================================================================
// END
// ================================================================
