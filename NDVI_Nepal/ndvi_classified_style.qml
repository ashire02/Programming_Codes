<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>
<qgis version="3.28" styleCategories="AllStyleCategories" hasScaleBasedVisibilityFlag="0" minScale="1e+08" maxScale="0">
  <flags>
    <Identifiable>1</Identifiable>
    <Removable>1</Removable>
    <Searchable>1</Searchable>
    <Private>0</Private>
  </flags>
  <pipe-data-defined-properties>
    <Option type="Map">
      <Option name="name" type="QString" value=""/>
      <Option name="properties"/>
      <Option name="type" type="QString" value="collection"/>
    </Option>
  </pipe-data-defined-properties>
  <pipe>
    <provider>
      <resampling zoomedOutResamplingMethod="nearestNeighbour" maxOversampling="2"
                  zoomedInResamplingMethod="nearestNeighbour" enabled="false"/>
    </provider>
    <rasterrenderer type="paletted" opacity="1" alphaBand="-1" band="1" nodataColor="">
      <rasterTransparency/>
      <minMaxOrigin>
        <limits>None</limits>
        <extent>WholeRaster</extent>
        <statAccuracy>Estimated</statAccuracy>
        <cumulativeCutLower>0.02</cumulativeCutLower>
        <cumulativeCutUpper>0.98</cumulativeCutUpper>
        <stdDevFactor>2</stdDevFactor>
      </minMaxOrigin>
      <colorPalette>
        <paletteEntry value="1" color="#4575b4" alpha="255" label="Water / Snow (&lt; 0.0)"/>
        <paletteEntry value="2" color="#d73027" alpha="255" label="Bare soil / Built-up (0.0–0.1)"/>
        <paletteEntry value="3" color="#fdae61" alpha="255" label="Very sparse vegetation (0.1–0.2)"/>
        <paletteEntry value="4" color="#fee08b" alpha="255" label="Moderate vegetation (0.2–0.4)"/>
        <paletteEntry value="5" color="#74c476" alpha="255" label="Dense vegetation (0.4–0.6)"/>
        <paletteEntry value="6" color="#238b45" alpha="255" label="Very dense / Healthy forest (&gt; 0.6)"/>
      </colorPalette>
      <colorramp name="[source]" type="randomcolors">
        <Option/>
      </colorramp>
    </rasterrenderer>
    <brightnesscontrast brightness="0" gamma="1" contrast="0"/>
    <huesaturation grayscaleMode="0" colorizeStrength="100" colorizeBlue="128"
                   colorizeRed="255" saturation="0" colorizeGreen="128"
                   invertColors="0" colorizeOn="0"/>
    <rasterresampler maxOversampling="2"/>
    <resamplingStage>resamplingFilter</resamplingStage>
  </pipe>
  <blendMode>0</blendMode>
</qgis>
