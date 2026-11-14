<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import L from 'leaflet'

const props = defineProps({
  active: { type: Boolean, default: true },
})
const emit = defineEmits(['go-back', 'continue'])

const mapElement = ref(null)
const points = ref([])
const fields = ref([])
const drawing = ref(true)
const fieldName = ref('Field 1')
const locating = ref(false)
const message = ref('')
let map
let pointLayer
let boundaryLayer

const canConfirm = computed(() => points.value.length >= 3)
const fieldCountLabel = computed(() => `${fields.value.length} ${fields.value.length === 1 ? 'field' : 'fields'}`)

function drawBoundary() {
  pointLayer.clearLayers()
  boundaryLayer.clearLayers()

  function addPointMarkers(fieldPoints, radius = 5) {
    for (const point of fieldPoints) {
      L.circleMarker(point, {
        radius,
        color: '#ffffff',
        weight: 2,
        fillColor: '#285a3c',
        fillOpacity: 1,
        bubblingMouseEvents: false,
      }).addTo(pointLayer)
    }
  }

  for (const field of fields.value) {
    L.polygon(field.boundary, {
      color: '#285a3c',
      weight: 3,
      fillColor: '#6c9b6c',
      fillOpacity: 0.2,
      bubblingMouseEvents: false,
    }).addTo(boundaryLayer)
    addPointMarkers(field.boundary)
  }

  addPointMarkers(points.value, 6)

  if (points.value.length >= 2) {
    const shape = points.value.length >= 3 ? L.polygon : L.polyline
    shape(points.value, {
      color: '#285a3c',
      weight: 3,
      fillColor: '#6c9b6c',
      fillOpacity: 0.3,
      bubblingMouseEvents: false,
    }).addTo(boundaryLayer)
  }
}

function addPoint(event) {
  if (!drawing.value || locating.value) return
  points.value.push(event.latlng)
  message.value = ''
  drawBoundary()
}

function undoPoint() {
  points.value.pop()
  message.value = ''
  drawBoundary()
}

function clearPoints() {
  points.value = []
  message.value = ''
  drawBoundary()
}

function confirmField() {
  if (!canConfirm.value) return
  const name = fieldName.value.trim() || `Field ${fields.value.length + 1}`
  fields.value.push({
    name,
    boundary: points.value.map(({ lat, lng }) => ({ lat, lng })),
  })
  points.value = []
  drawing.value = false
  message.value = `${name} added.`
  drawBoundary()
}

function addAnotherField() {
  points.value = []
  fieldName.value = `Field ${fields.value.length + 1}`
  drawing.value = true
  message.value = ''
  drawBoundary()
}

function cancelCurrentOutline() {
  points.value = []
  drawing.value = false
  message.value = ''
  drawBoundary()
}

function continueToFieldInfo() {
  if (fields.value.length > 0) emit('continue', fields.value)
}

function findMyLocation() {
  if (!navigator.geolocation) {
    message.value = 'Location is not available in this browser. You can move the map by hand.'
    return
  }

  locating.value = true
  message.value = 'Finding your location…'
  navigator.geolocation.getCurrentPosition(
    ({ coords }) => {
      map.setView([coords.latitude, coords.longitude], 16)
      locating.value = false
      message.value = ''
    },
    () => {
      locating.value = false
      message.value = 'Could not get your location. You can move the map by hand.'
    },
    { enableHighAccuracy: true, timeout: 10000 },
  )
}

onMounted(() => {
  map = L.map(mapElement.value, { zoomControl: true }).setView([20, 0], 2)
  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  }).addTo(map)
  pointLayer = L.layerGroup().addTo(map)
  boundaryLayer = L.layerGroup().addTo(map)
  map.on('click', addPoint)
  requestAnimationFrame(() => map.invalidateSize())
  findMyLocation()
})

watch(() => props.active, async (active) => {
  if (!active) return
  await nextTick()
  map?.invalidateSize()
})

onBeforeUnmount(() => {
  map?.off('click', addPoint)
  map?.remove()
})
</script>

<template>
  <main class="page-shell">
    <header class="brand" aria-label="Field Shift">
      <span class="brand-mark" aria-hidden="true">
        <svg viewBox="0 0 40 40" fill="none">
          <path d="M7 31c6.5-1.2 12.7-4 18.2-8.1C29.3 20.1 33 15 34 9" />
          <path d="M7 24.5c5.1-1 9.7-3.2 13.8-6.2C24.6 15.6 27.3 12 29 7" />
          <path d="M7 17.5c3.5-.8 6.7-2.2 9.5-4.2 2-1.4 3.7-3 5.1-4.8" />
        </svg>
      </span>
      <span>Field Shift</span>
    </header>

    <section class="map-page" aria-labelledby="map-title">
      <div class="map-page-header">
        <button class="back-button" type="button" @click="emit('go-back')">
          <span aria-hidden="true">←</span> Back
        </button>
        <div class="map-page-title">
          <h1 id="map-title">Choose your fields</h1>
          <p>Outline each field on the map. You can add more than one.</p>
        </div>
        <button class="secondary-button location-button" type="button" @click="findMyLocation">
          <span aria-hidden="true">◎</span> Use my location
        </button>
      </div>

      <div class="field-workspace">
        <div class="map-frame">
          <div ref="mapElement" class="field-map" aria-label="Map for selecting and outlining fields"></div>
          <div v-if="locating" class="map-loading" role="status" aria-live="polite">
            <span class="loading-spinner" aria-hidden="true"></span>
            <div>
              <strong>Finding your location…</strong>
              <p>This can take a few seconds.</p>
            </div>
          </div>
        </div>

        <aside class="field-panel" aria-label="Field outline controls">
          <p v-if="drawing">
            <strong>{{ fields.length ? `Add field ${fields.length + 1}` : 'Draw your first field' }}</strong>
            Tap at least 3 corners on the map. Then name the field and tap OK.
          </p>
          <p v-else>
            <strong>{{ fieldCountLabel }} added</strong>
            Add another field or continue to field information.
          </p>

          <label v-if="drawing" class="field-name-input" for="field-name">
            Field name
            <input id="field-name" v-model="fieldName" type="text" :placeholder="`Field ${fields.length + 1}`" maxlength="60" />
          </label>

          <div v-if="fields.length > 0" class="field-list" aria-label="Fields added">
            <p class="field-list-title">Fields added</p>
            <div v-for="(field, index) in fields" :key="index" class="field-list-item">
              <span class="field-list-number">{{ index + 1 }}</span>
              <span>{{ field.name }}</span>
            </div>
          </div>

          <p v-if="drawing" class="points-count" aria-live="polite">
            {{ points.length }} {{ points.length === 1 ? 'point' : 'points' }} marked
          </p>

          <div v-if="drawing" class="field-panel-actions">
            <button class="secondary-button" type="button" :disabled="points.length === 0" @click="undoPoint">
              Undo point
            </button>
            <button class="secondary-button" type="button" :disabled="points.length === 0" @click="clearPoints">
              Clear outline
            </button>
            <button class="primary-button" type="button" :disabled="!canConfirm" @click="confirmField">
              OK <span aria-hidden="true">✓</span>
            </button>
            <button v-if="fields.length > 0" class="cancel-outline-button" type="button" @click="cancelCurrentOutline">
              Cancel this outline
            </button>
          </div>

          <div v-else class="field-panel-actions">
            <button class="secondary-button" type="button" @click="addAnotherField">
              <span aria-hidden="true">＋</span> Add field
            </button>
            <button class="primary-button" type="button" @click="continueToFieldInfo">
              Next <span aria-hidden="true">→</span>
            </button>
          </div>

          <p v-if="message && !locating" class="map-status" role="status">{{ message }}</p>
        </aside>
      </div>
    </section>
  </main>
</template>
