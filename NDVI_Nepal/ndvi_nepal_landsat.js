// ================================================================
//  NDVI Analysis — Nepal  |  Landsat 5 / 8 / 9  |  1990 – 2025
//  Asset : projects/ashire02/assets/Nepal
//  UI    : Interactive side-panel  (split-panel layout)
// ================================================================
//
//  Landsat availability used in this script
//  ─────────────────────────────────────────
//  Landsat 5 TM  (SR_B3=Red, SR_B4=NIR)
//    Collection : LANDSAT/LT05/C02/T1_L2
//    Available  : 1984-03-01 → 2013-05-05
//
//  Landsat 8 OLI (SR_B4=Red, SR_B5=NIR)
//    Collection : LANDSAT/LC08/C02/T1_L2
//    Available  : 2013-04-11 → present
//
//  Landsat 9 OLI-2 (SR_B4=Red, SR_B5=NIR)
//    Collection : LANDSAT/LC09/C02/T1_L2
//    Launched   : 2021-09-27  |  Science ops: 2022-02-10
//    Used from  : 2022-10-01  (1 year after launch)
// ================================================================

// ── Sensor date boundaries ──────────────────────────────────────
var L5_START = '1984-03-01';
var L5_END   = '2013-05-05';
var L8_START = '2013-04-11';
var L9_START = '2022-10-01'; // 1 year after launch (2021-09-27)

// ── NDVI classification thresholds ─────────────────────────────
var THRESHOLDS = [
  {max: 0.0,  cls: 1, color: '#4575b4', label: '< 0.0   Water / Snow / Non-vegetated'},
  {max: 0.1,  cls: 2, color: '#d73027', label: '0.0–0.1  Bare soil / Built-up'},
  {max: 0.2,  cls: 3, color: '#fdae61', label: '0.1–0.2  Very sparse vegetation'},
  {max: 0.4,  cls: 4, color: '#fee08b', label: '0.2–0.4  Moderate vegetation'},
  {max: 0.6,  cls: 5, color: '#74c476', label: '0.4–0.6  Dense vegetation'},
  {max: 1.0,  cls: 6, color: '#238b45', label: '> 0.6   Very dense / Healthy forest'}
];

// ── Season month windows ────────────────────────────────────────
var SEASONS = {
  'Annual (Jan–Dec)': {start: '01-01', end: '12-31'},
  'Dry/Winter (Oct–Apr)': {start: '10-01', end: '04-30'},
  'Pre-Monsoon (Mar–May)': {start: '03-01', end: '05-31'},
  'Monsoon (Jun–Sep)': {start: '06-01', end: '09-30'},
  'Post-Monsoon (Oct–Nov)': {start: '10-01', end: '11-30'}
};

// ================================================================
//  1.  LAYOUT — clear default UI, build split panel
// ================================================================
ui.root.clear();

var mapPanel  = ui.Map();
mapPanel.setOptions('HYBRID');
mapPanel.setControlVisibility({all: true});

var sidePanel = ui.Panel({
  layout: ui.Panel.Layout.flow('vertical'),
  style : {
    width          : '320px',
    padding        : '8px',
    backgroundColor: '#1e1e2e'
  }
});

var splitPanel = ui.SplitPanel({
  firstPanel : sidePanel,
  secondPanel: mapPanel,
  orientation: 'horizontal',
  wipe       : false
});

ui.root.add(splitPanel);

// ================================================================
//  2.  HELPER — styled widgets
// ================================================================
function makeLabel(text, style) {
  return ui.Label(text, style || {color:'#cdd6f4', fontSize:'13px'});
}
function makeTitle(text) {
  return ui.Label(text, {
    color     : '#89dceb',
    fontSize  : '15px',
    fontWeight: 'bold',
    margin    : '6px 0 2px 0'
  });
}
function makeDivider() {
  return ui.Label('─────────────────────────', {
    color : '#45475a',
    margin: '4px 0'
  });
}
function statusLabel(text, color) {
  return ui.Label(text || '', {
    color     : color || '#a6e3a1',
    fontSize  : '11px',
    whiteSpace: 'pre'
  });
}

// ================================================================
//  3.  WIDGETS
// ================================================================

// ── Title ────────────────────────────────────────────────────────
sidePanel.add(makeLabel('NDVI ANALYSIS — NEPAL', {
  color: '#cba6f7', fontSize: '16px', fontWeight: 'bold', margin: '4px 0'
}));
sidePanel.add(makeLabel('Landsat 5 / 8 / 9  |  1990 – 2025', {
  color: '#bac2de', fontSize: '11px', margin: '0 0 6px 0'
}));
sidePanel.add(makeDivider());

// ── Year selectors ───────────────────────────────────────────────
sidePanel.add(makeTitle('Date Range'));

var years = [];
for (var y = 1990; y <= 2025; y++) years.push(String(y));

var startYearSel = ui.Select({
  items      : years,
  value      : '2020',
  placeholder: 'Start year',
  style      : {width: '130px', color: '#1e1e2e'}
});
var endYearSel = ui.Select({
  items      : years,
  value      : '2024',
  placeholder: 'End year',
  style      : {width: '130px', color: '#1e1e2e'}
});

var yearRow = ui.Panel([
  ui.Panel([makeLabel('Start'), startYearSel],
           ui.Panel.Layout.flow('vertical'), {margin:'0 6px 0 0'}),
  ui.Panel([makeLabel('End'),   endYearSel  ],
           ui.Panel.Layout.flow('vertical'))
], ui.Panel.Layout.flow('horizontal'));
sidePanel.add(yearRow);

// ── Season ───────────────────────────────────────────────────────
sidePanel.add(makeTitle('Season'));
var seasonSel = ui.Select({
  items : Object.keys(SEASONS),
  value : 'Annual (Jan–Dec)',
  style : {color: '#1e1e2e'}
});
sidePanel.add(seasonSel);

// ── Cloud cover ──────────────────────────────────────────────────
sidePanel.add(makeTitle('Max Cloud Cover (%)'));
var cloudSlider = ui.Slider({
  min: 5, max: 80, value: 20, step: 5,
  style: {stretch: 'horizontal'}
});
var cloudLabel = makeLabel('20 %', {color:'#f38ba8', fontSize:'12px'});
cloudSlider.onSlide(function(v) { cloudLabel.setValue(String(Math.round(v)) + ' %'); });
sidePanel.add(ui.Panel([cloudSlider, cloudLabel], ui.Panel.Layout.flow('horizontal')));

// ── Composite method ─────────────────────────────────────────────
sidePanel.add(makeTitle('Composite Method'));
var methodSel = ui.Select({
  items: ['Median', 'Mean', 'Max (Greenest pixel)'],
  value: 'Median',
  style: {color: '#1e1e2e'}
});
sidePanel.add(methodSel);

// ── Display layer ─────────────────────────────────────────────────
sidePanel.add(makeTitle('Display Layer'));
var displaySel = ui.Select({
  items: ['Continuous NDVI', 'Classified NDVI (6 classes)', 'Both'],
  value: 'Both',
  style: {color: '#1e1e2e'}
});
sidePanel.add(displaySel);

sidePanel.add(makeDivider());

// ── Sensor info panel (populated on Run) ────────────────────────
sidePanel.add(makeTitle('Active Sensors'));
var sensorInfoPanel = ui.Panel({style: {margin: '0 0 4px 0'}});
sensorInfoPanel.add(makeLabel('Press Run to detect sensors', {
  color: '#6c7086', fontSize: '11px'
}));
sidePanel.add(sensorInfoPanel);

sidePanel.add(makeDivider());

// ── RUN button ───────────────────────────────────────────────────
var runButton = ui.Button({
  label : '▶  Run Analysis',
  style : {
    stretch        : 'horizontal',
    color          : '#1e1e2e',
    backgroundColor: '#a6e3a1',
    fontWeight     : 'bold',
    fontSize       : '14px',
    margin         : '4px 0'
  }
});
sidePanel.add(runButton);

// ── Status label ─────────────────────────────────────────────────
var statusPanel = ui.Panel({style: {minHeight: '20px'}});
sidePanel.add(statusPanel);

sidePanel.add(makeDivider());

// ── Statistics panel ─────────────────────────────────────────────
sidePanel.add(makeTitle('NDVI Statistics'));
var statsPanel = ui.Panel({style: {backgroundColor:'#181825', padding:'6px'}});
statsPanel.add(makeLabel('Run analysis to see stats', {color:'#6c7086', fontSize:'11px'}));
sidePanel.add(statsPanel);

sidePanel.add(makeDivider());

// ── Legend ────────────────────────────────────────────────────────
sidePanel.add(makeTitle('Classification Legend'));
var legendPanel = ui.Panel();
THRESHOLDS.forEach(function(t) {
  var row = ui.Panel([
    ui.Label('', {
      backgroundColor: t.color,
      padding        : '7px 12px',
      margin         : '1px 6px 1px 0'
    }),
    makeLabel(t.label, {color:'#cdd6f4', fontSize:'10px'})
  ], ui.Panel.Layout.flow('horizontal'), {margin:'1px 0'});
  legendPanel.add(row);
});
sidePanel.add(legendPanel);

sidePanel.add(makeDivider());

// ── Export button ─────────────────────────────────────────────────
sidePanel.add(makeTitle('Export'));
var exportContSel = ui.Select({
  items: ['Continuous NDVI', 'Classified NDVI'],
  value: 'Continuous NDVI',
  style: {color: '#1e1e2e'}
});
sidePanel.add(exportContSel);

var exportButton = ui.Button({
  label : '⬇  Export to Drive',
  style : {
    stretch        : 'horizontal',
    color          : '#1e1e2e',
    backgroundColor: '#89b4fa',
    fontWeight     : 'bold',
    margin         : '4px 0'
  }
});
sidePanel.add(exportButton);
var exportStatus = makeLabel('', {color:'#fab387', fontSize:'11px'});
sidePanel.add(exportStatus);

sidePanel.add(makeDivider());
sidePanel.add(makeLabel('Asset: projects/ashire02/assets/Nepal', {
  color: '#6c7086', fontSize: '10px'
}));

// ================================================================
//  4.  CORE PROCESSING FUNCTIONS
// ================================================================

// ── Load AOI ─────────────────────────────────────────────────────
var nepal = ee.FeatureCollection('projects/ashire02/assets/Nepal');
var aoi   = nepal.geometry();

// ── Cloud mask: Landsat 5 (QA_PIXEL) ────────────────────────────
function maskL5(image) {
  var qa   = image.select('QA_PIXEL');
  var mask = qa.bitwiseAnd(1 << 3).eq(0)  // cloud shadow
               .and(qa.bitwiseAnd(1 << 4).eq(0))  // snow
               .and(qa.bitwiseAnd(1 << 5).eq(0));  // cloud
  return image.updateMask(mask)
    .select(['SR_B3', 'SR_B4'])
    .multiply(0.0000275).add(-0.2)
    // Rename to common band names for NDVI
    .rename(['Red', 'NIR'])
    .copyProperties(image, ['system:time_start']);
}

// ── Cloud mask: Landsat 8 / 9 (QA_PIXEL) ────────────────────────
function maskL89(image) {
  var qa   = image.select('QA_PIXEL');
  var mask = qa.bitwiseAnd(1 << 3).eq(0)
               .and(qa.bitwiseAnd(1 << 4).eq(0))
               .and(qa.bitwiseAnd(1 << 5).eq(0));
  return image.updateMask(mask)
    .select(['SR_B4', 'SR_B5'])
    .multiply(0.0000275).add(-0.2)
    .rename(['Red', 'NIR'])
    .copyProperties(image, ['system:time_start']);
}

// ── NDVI band ─────────────────────────────────────────────────────
function computeNDVI(image) {
  return image.normalizedDifference(['NIR', 'Red']).rename('NDVI')
    .copyProperties(image, ['system:time_start']);
}

// ── Build date filter for a season spanning year boundaries ──────
//   e.g. Dry season Oct–Apr needs two filters joined with OR
function buildDateFilter(startYear, endYear, seasonKey) {
  var s = SEASONS[seasonKey];
  var filters = [];

  if (s.start <= s.end) {
    // Season within same calendar year
    for (var yr = startYear; yr <= endYear; yr++) {
      filters.push(ee.Filter.date(
        yr + '-' + s.start,
        yr + '-' + s.end
      ));
    }
  } else {
    // Season spans year boundary (e.g. Oct–Apr: Oct yr → Apr yr+1)
    for (var yr = startYear; yr < endYear; yr++) {
      filters.push(ee.Filter.date(
        yr       + '-' + s.start,
        (yr + 1) + '-' + s.end
      ));
    }
    // Partial last window: Oct of endYear → Dec 31 endYear
    filters.push(ee.Filter.date(
      endYear + '-' + s.start,
      endYear + '-12-31'
    ));
  }

  return ee.Filter.or.apply(null, filters);
}

// ── Classify NDVI image ───────────────────────────────────────────
function classifyNDVI(ndvi) {
  var cls = ndvi.where(ndvi.lt(0.0), 1)
               .where(ndvi.gte(0.0).and(ndvi.lt(0.1)), 2)
               .where(ndvi.gte(0.1).and(ndvi.lt(0.2)), 3)
               .where(ndvi.gte(0.2).and(ndvi.lt(0.4)), 4)
               .where(ndvi.gte(0.4).and(ndvi.lt(0.6)), 5)
               .where(ndvi.gte(0.6), 6);
  return cls.rename('NDVI_Class');
}

// ================================================================
//  5.  GLOBAL STATE  (shared between Run and Export)
// ================================================================
var currentNDVI       = null;
var currentClassified = null;
var currentLabel      = '';

// ================================================================
//  6.  RUN BUTTON CALLBACK
// ================================================================
runButton.onClick(function() {

  // ── Read widget values ──────────────────────────────────────
  var startYear  = parseInt(startYearSel.getValue(),  10);
  var endYear    = parseInt(endYearSel.getValue(),    10);
  var cloud      = cloudSlider.getValue();
  var seasonKey  = seasonSel.getValue();
  var method     = methodSel.getValue();
  var display    = displaySel.getValue();

  if (startYear > endYear) {
    statusPanel.clear();
    statusPanel.add(statusLabel('⚠ Start year must be ≤ End year', '#f38ba8'));
    return;
  }

  statusPanel.clear();
  statusPanel.add(statusLabel('⏳ Building collection…', '#f9e2af'));

  // ── Determine which sensors cover the selected range ─────────
  var rangeStart = ee.Date(startYear + '-01-01');
  var rangeEnd   = ee.Date(endYear   + '-12-31');

  var useL5 = (startYear <= 2013);           // L5 ends May 2013
  var useL8 = (endYear   >= 2013);           // L8 starts Apr 2013
  var useL9 = (endYear   >= 2022);           // L9 usable from Oct 2022

  // ── Update sensor info ────────────────────────────────────────
  sensorInfoPanel.clear();
  var sensorLines = [];
  if (useL5) sensorLines.push('✔ Landsat 5  (1990 – May 2013)');
  if (useL8) sensorLines.push('✔ Landsat 8  (Apr 2013 – present)');
  if (useL9) sensorLines.push('✔ Landsat 9  (Oct 2022 – present)');
  sensorLines.forEach(function(s) {
    sensorInfoPanel.add(makeLabel(s, {color: '#a6e3a1', fontSize: '11px'}));
  });

  // ── Season date filter ────────────────────────────────────────
  var dateFilter = buildDateFilter(startYear, endYear, seasonKey);

  // ── Load and mask each sensor ─────────────────────────────────
  var collections = [];

  if (useL5) {
    var l5 = ee.ImageCollection('LANDSAT/LT05/C02/T1_L2')
      .filterBounds(aoi)
      .filter(dateFilter)
      .filter(ee.Filter.date(L5_START, L5_END))
      .filter(ee.Filter.lt('CLOUD_COVER', cloud))
      .map(maskL5)
      .map(computeNDVI);
    collections.push(l5);
  }

  if (useL8) {
    var l8 = ee.ImageCollection('LANDSAT/LC08/C02/T1_L2')
      .filterBounds(aoi)
      .filter(dateFilter)
      .filter(ee.Filter.date(L8_START, '2025-12-31'))
      .filter(ee.Filter.lt('CLOUD_COVER', cloud))
      .map(maskL89)
      .map(computeNDVI);
    collections.push(l8);
  }

  if (useL9) {
    var l9 = ee.ImageCollection('LANDSAT/LC09/C02/T1_L2')
      .filterBounds(aoi)
      .filter(dateFilter)
      .filter(ee.Filter.date(L9_START, '2025-12-31'))
      .filter(ee.Filter.lt('CLOUD_COVER', cloud))
      .map(maskL89)
      .map(computeNDVI);
    collections.push(l9);
  }

  // Merge all available sensors
  var merged = collections[0];
  for (var i = 1; i < collections.length; i++) {
    merged = merged.merge(collections[i]);
  }

  // ── Composite ─────────────────────────────────────────────────
  var composite;
  if      (method === 'Mean')                 composite = merged.mean();
  else if (method === 'Max (Greenest pixel)') composite = merged.max();
  else                                        composite = merged.median();

  var ndviImage = composite.clip(aoi).rename('NDVI');

  // Stash for export
  currentNDVI       = ndviImage;
  currentClassified = classifyNDVI(ndviImage);
  currentLabel      = startYear + '_' + endYear + '_' +
                      seasonKey.replace(/[^a-zA-Z0-9]/g, '_');

  // ── Vis params ────────────────────────────────────────────────
  var ndviVis = {
    min    : -0.2,
    max    : 0.8,
    palette: ['#d73027','#fc8d59','#fee08b','#d9ef8b','#91cf60','#1a9850']
  };
  var classVis = {
    min    : 1,
    max    : 6,
    palette: THRESHOLDS.map(function(t) { return t.color; })
  };

  // ── Clear old layers, add new ─────────────────────────────────
  mapPanel.layers().reset();
  mapPanel.addLayer(nepal, {color: 'ffffff', fillColor: '00000000'}, 'Nepal Boundary');

  if (display === 'Continuous NDVI' || display === 'Both') {
    mapPanel.addLayer(ndviImage, ndviVis, 'NDVI Continuous');
  }
  if (display === 'Classified NDVI (6 classes)' || display === 'Both') {
    mapPanel.addLayer(currentClassified, classVis, 'NDVI Classified');
  }

  mapPanel.centerObject(aoi, 7);
  statusPanel.clear();
  statusPanel.add(statusLabel('✔ Map updated', '#a6e3a1'));

  // ── Statistics (async, won't freeze UI) ──────────────────────
  statsPanel.clear();
  statsPanel.add(makeLabel('Computing…', {color:'#f9e2af', fontSize:'11px'}));

  var stats = ndviImage.reduceRegion({
    reducer   : ee.Reducer.mean()
                  .combine(ee.Reducer.min(),    '', true)
                  .combine(ee.Reducer.max(),    '', true)
                  .combine(ee.Reducer.stdDev(), '', true),
    geometry  : aoi,
    scale     : 500,   // coarser scale keeps UI responsive
    maxPixels : 1e11,
    bestEffort: true
  });

  stats.evaluate(function(result, err) {
    statsPanel.clear();
    if (err) {
      statsPanel.add(makeLabel('Stats error: ' + err, {color:'#f38ba8', fontSize:'11px'}));
      return;
    }
    if (!result) {
      statsPanel.add(makeLabel('No data for this selection.', {color:'#f38ba8', fontSize:'11px'}));
      return;
    }
    var fmt = function(v) { return v !== undefined ? v.toFixed(4) : 'N/A'; };
    var lines = [
      'Mean   : ' + fmt(result.NDVI_mean),
      'Min    : ' + fmt(result.NDVI_min),
      'Max    : ' + fmt(result.NDVI_max),
      'StdDev : ' + fmt(result.NDVI_stdDev)
    ];
    lines.forEach(function(l) {
      statsPanel.add(makeLabel(l, {
        color      : '#cdd6f4',
        fontSize   : '12px',
        fontFamily : 'monospace'
      }));
    });
  });

  // ── Scene count (async) ───────────────────────────────────────
  merged.size().evaluate(function(count, err) {
    if (!err && count !== null) {
      statusPanel.clear();
      statusPanel.add(statusLabel(
        '✔ Done  |  ' + count + ' scenes used', '#a6e3a1'
      ));
    }
  });
});

// ================================================================
//  7.  EXPORT BUTTON CALLBACK
// ================================================================
exportButton.onClick(function() {
  if (!currentNDVI) {
    exportStatus.setValue('⚠ Run the analysis first.');
    return;
  }
  var choice = exportContSel.getValue();
  var img    = (choice === 'Classified NDVI') ? currentClassified : currentNDVI;
  var desc   = (choice === 'Classified NDVI')
    ? 'Nepal_NDVI_Classified_' + currentLabel
    : 'Nepal_NDVI_Continuous_' + currentLabel;

  Export.image.toDrive({
    image          : img,
    description    : desc,
    folder         : 'GEE_Exports',
    fileNamePrefix : desc,
    region         : aoi,
    scale          : 30,
    crs            : 'EPSG:4326',
    maxPixels      : 1e13
  });

  exportStatus.setValue('✔ Export task submitted.\nCheck Tasks tab (top-right).');
});

// ================================================================
//  8.  INITIAL MAP SETUP
// ================================================================
mapPanel.centerObject(
  ee.FeatureCollection('projects/ashire02/assets/Nepal').geometry(), 7
);
mapPanel.addLayer(
  ee.FeatureCollection('projects/ashire02/assets/Nepal'),
  {color: 'ffffff', fillColor: '00000000'},
  'Nepal Boundary'
);

// ================================================================
// END OF SCRIPT
// ================================================================
