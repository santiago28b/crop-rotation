<script setup>
// NASA satellite layers for the field map, straight from GIBS (no API key).
// "Satellite photo" = MODIS Terra true color, daily, 250 m.
// "Plant health"    = MODIS NDVI 8-day composite: green = growing plants.
// The slider walks the 2025 growing season (April-October) so a farmer can
// watch the valley green up and dry down. MODIS is 250 m, so tiles soften
// when you zoom to a single field - the pattern is the point, not the pixels.
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import L from 'leaflet'

const props = defineProps({ map: { type: Object, default: null } })

const GIBS = 'https://gibs.earthdata.nasa.gov/wmts/epsg3857/best'
const LAYERS = {
  photo: { id: 'MODIS_Terra_CorrectedReflectance_TrueColor', ext: 'jpg', opacity: 1.0, label: 'Satellite photo' },
  ndvi: { id: 'MODIS_Terra_NDVI_8Day', ext: 'png', opacity: 0.75, label: 'Plant health' },
}

// MODIS 8-day periods are anchored to Jan 1; use those dates so NDVI tiles
// always exist. True color is daily, so these dates work for it too.
const dates = (() => {
  const out = []
  const jan1 = Date.UTC(2025, 0, 1)
  for (let doy = 0; doy < 365; doy += 8) {
    const d = new Date(jan1 + doy * 86400000)
    const month = d.getUTCMonth()
    if (month >= 3 && month <= 9) out.push(d) // April-October
  }
  return out
})()

const panel = ref(null)
onMounted(() => {
  // the panel floats on the map: keep its clicks/drags from drawing field points
  if (panel.value) {
    L.DomEvent.disableClickPropagation(panel.value)
    L.DomEvent.disableScrollPropagation(panel.value)
  }
})

const mode = ref('off')
const index = ref(Math.floor(dates.length / 2)) // start mid-season (July)
let tiles = null

const dateISO = computed(() => dates[index.value].toISOString().slice(0, 10))
const dateLabel = computed(() =>
  dates[index.value].toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric', timeZone: 'UTC' }))

function tileUrl() {
  const layer = LAYERS[mode.value]
  return `${GIBS}/${layer.id}/default/${dateISO.value}/GoogleMapsCompatible_Level9/{z}/{y}/{x}.${layer.ext}`
}

function refresh() {
  if (!props.map) return
  if (mode.value === 'off') {
    if (tiles) { props.map.removeLayer(tiles); tiles = null }
    return
  }
  if (tiles && tiles.options._mode === mode.value) {
    tiles.setUrl(tileUrl())                 // date moved: swap tiles in place
    return
  }
  if (tiles) props.map.removeLayer(tiles)
  tiles = L.tileLayer(tileUrl(), {
    maxNativeZoom: 9,                       // MODIS stops at z9; upscale past it
    maxZoom: 19,
    opacity: LAYERS[mode.value].opacity,
    attribution: 'NASA EOSDIS <a href="https://earthdata.nasa.gov/gibs">GIBS</a>',
    _mode: mode.value,
  }).addTo(props.map)
}

watch([mode, index, () => props.map], refresh)
onBeforeUnmount(() => { if (tiles && props.map) props.map.removeLayer(tiles) })

function setMode(next) {
  mode.value = mode.value === next ? 'off' : next
}
</script>

<template>
  <div ref="panel" class="sat-panel" aria-label="NASA satellite layers">
    <div class="sat-buttons">
      <span class="sat-title">🛰️ NASA layers</span>
      <button type="button" :class="{ on: mode === 'photo' }" @click="setMode('photo')">Satellite photo</button>
      <button type="button" :class="{ on: mode === 'ndvi' }" @click="setMode('ndvi')">Plant health</button>
    </div>
    <label v-if="mode !== 'off'" class="sat-slider">
      <input v-model.number="index" type="range" :min="0" :max="dates.length - 1" step="1"
             :aria-label="`Season date: ${dateLabel}`" />
      <span class="sat-date">{{ dateLabel }}</span>
    </label>
    <p v-if="mode === 'ndvi'" class="sat-hint">
      Green = growing plants (MODIS NDVI, 250 m). Drag the slider to watch the season.
    </p>
  </div>
</template>

<style scoped>
.sat-panel {
  position: absolute;
  left: 10px;
  bottom: 10px;
  z-index: 1100;            /* above Leaflet panes and controls */
  max-width: min(420px, calc(100% - 20px));
  padding: 0.6rem 0.75rem;
  border: 1px solid rgba(0, 0, 0, 0.12);
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.95);
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.18);
  display: flex;
  flex-direction: column;
  gap: 0.45rem;
  font-size: 0.85rem;
}
.sat-buttons {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}
.sat-title { font-weight: 600; }
.sat-buttons button {
  padding: 0.3rem 0.7rem;
  border-radius: 999px;
  border: 1px solid rgba(0, 0, 0, 0.25);
  background: #fff;
  cursor: pointer;
  font: inherit;
}
.sat-buttons button.on {
  background: #1a3c8f;
  border-color: #1a3c8f;
  color: #fff;
}
.sat-slider {
  display: flex;
  align-items: center;
  gap: 0.6rem;
}
.sat-slider input { flex: 1; }
.sat-date { min-width: 7.5em; font-variant-numeric: tabular-nums; }
.sat-hint { margin: 0; opacity: 0.75; }
</style>
