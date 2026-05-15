# NDVI Analysis — Nepal (Google Earth Engine)

Year-by-year NDVI mapping over Nepal using **Landsat 5 / 8 / 9** Surface Reflectance.  
Plain side-panel UI with Prev/Next year navigation.

---

## Sensor Coverage

| Sensor | Collection | Red | NIR | Period used |
|---|---|---|---|---|
| Landsat 5 TM | `LANDSAT/LT05/C02/T1_L2` | SR_B3 | SR_B4 | 1990 – May 2013 |
| Landsat 8 OLI | `LANDSAT/LC08/C02/T1_L2` | SR_B4 | SR_B5 | Apr 2013 – present |
| Landsat 9 OLI-2 | `LANDSAT/LC09/C02/T1_L2` | SR_B4 | SR_B5 | Oct 2022 – present |

Sensor selection is automatic based on the chosen year. Overlap years merge all valid sensors.

---

## Panel Controls

| Control | Description |
|---|---|
| **◀ Prev / Next ▶** | Step one year back or forward |
| **Year slider** | Jump directly to any year 1990–2025 |
| **Season** | Annual, Dry/Winter, Pre-Monsoon, Monsoon, Post-Monsoon |
| **Max Cloud Cover** | Slider 5–80 % |
| **Composite Method** | Median / Mean / Max (greenest pixel) |
| **Display Layer** | Continuous NDVI, Classified NDVI, or Both |
| **▶ Run** | Build and show the selected year's NDVI |
| **NDVI Statistics** | Mean, Min, Max, StdDev (async, non-blocking) |
| **⬇ Export** | Save 30 m GeoTIFF to Google Drive (`GEE_Exports/`) |

---

## NDVI Classification

| Class | Range | Cover type |
|---|---|---|
| 1 | < 0.0 | Water / Snow |
| 2 | 0.0 – 0.1 | Bare soil / Built-up |
| 3 | 0.1 – 0.2 | Very sparse vegetation |
| 4 | 0.2 – 0.4 | Moderate vegetation |
| 5 | 0.4 – 0.6 | Dense vegetation |
| 6 | > 0.6 | Very dense / Healthy forest |

---

## How to Run

1. Open [code.earthengine.google.com](https://code.earthengine.google.com/)
2. Paste `ndvi_nepal_landsat.js` into the Code Editor
3. Click **Run** — the split-panel loads
4. Pick a year, season, and options, then click **▶ Run**

---

## Asset

`projects/ashire02/assets/Nepal`
