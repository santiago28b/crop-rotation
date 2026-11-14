<script setup>
import { computed, onBeforeUnmount, reactive, ref, toRaw, watch } from 'vue'
import { getCatalog, getFieldProfile, isHistoryPending, pollFieldHistory } from '../api.js'

const props = defineProps({
  fields: { type: Array, required: true },
})
const emit = defineEmits(['go-back', 'continue'])

const years = [2021, 2022, 2023, 2024, 2025]
const cropOptions = ref([])
const catalogStatus = ref('loading')

const currentIndex = ref(0)
// One state object per field, kept across trips back to the map so answers and
// corrections survive adding or deleting other fields.
const statesByField = new WeakMap()
const controllers = new Map()
const fieldStates = ref([])

// The crop list loads on its own, so crops can be picked by hand while (or even if)
// the satellite lookup is slow or fails.
async function loadCatalog() {
  catalogStatus.value = 'loading'
  try {
    cropOptions.value = await getCatalog()
    catalogStatus.value = 'ready'
  } catch {
    catalogStatus.value = 'error'
  }
}
loadCatalog()

function applyHistory(state, history) {
  if (!history) return
  state.historyStatus = history.status
  state.historySource = history.source || ''
  state.historyNote = history.note || ''
  if (state.profile) state.profile.crop_history = history
  const estimates = new Map((history.years || []).map((entry) => [entry.year, entry]))
  for (const entry of state.answers.cropHistory) {
    const found = estimates.get(entry.year)
    if (!found) continue
    entry.estimate = { crop_id: found.crop_id || null, crop_label: found.crop_label, confidence: found.confidence }
    if (entry.source === 'farmer') continue // never overwrite what the farmer picked
    entry.crop_id = found.crop_id || ''
    entry.crop_label = found.crop_label
    entry.confidence = found.confidence
    entry.source = 'cdl'
  }
}

async function loadField(field, state, signal) {
  try {
    const profile = await getFieldProfile(field, { signal })
    state.profile = profile
    state.profileStatus = 'ready'
    const waterUse = profile.water_use
    if (waterUse?.looks_irrigated != null && !state.answers.waterTouched && !state.answers.irrigated) {
      state.answers.irrigated = waterUse.looks_irrigated ? 'yes' : 'no'
    }
    applyHistory(state, profile.crop_history)
    if (isHistoryPending(profile.crop_history)) {
      const last = await pollFieldHistory(field, { signal, onUpdate: (history) => applyHistory(state, history) })
      if (isHistoryPending(last)) state.historyStatus = 'timeout'
    }
  } catch (error) {
    if (signal.aborted) return
    if (state.profileStatus === 'loading') state.profileStatus = 'error'
    state.historyStatus = 'error'
    state.historyNote = error?.message || 'Request failed'
  }
}

function createFieldState(field) {
  const state = reactive({
    answers: {
      irrigated: '',            // '' = not sure, 'yes', 'no' (prefilled from satellite water use)
      irrigationMethod: '',     // 'drip' | 'sprinkler' | 'surface'
      waterSource: '',          // 'surface' (canal/river) | 'groundwater' (well) | 'mixed'
      waterTouched: false,      // farmer answered: never overwrite with a late prefill
      cropHistory: years.map((year) => ({
        year, crop_id: '', crop_label: 'Unknown', confidence: null, source: 'unknown', estimate: null,
      })),
    },
    profile: null,
    profileStatus: 'loading',
    historyStatus: 'loading',
    historySource: '',
    historyNote: '',
  })
  const controller = new AbortController()
  controllers.set(state, controller)
  loadField(field, state, controller.signal)
  return state
}

watch(() => [...props.fields], (fields) => {
  const next = fields.map((field) => {
    const key = toRaw(field)
    if (!statesByField.has(key)) statesByField.set(key, createFieldState(field))
    return statesByField.get(key)
  })
  for (const [state, controller] of controllers) {
    if (!next.includes(state)) {
      controller.abort()
      controllers.delete(state)
    }
  }
  fieldStates.value = next
  currentIndex.value = 0
}, { immediate: true })

onBeforeUnmount(() => {
  for (const controller of controllers.values()) controller.abort()
})

const currentState = computed(() => fieldStates.value[currentIndex.value])
const currentAnswers = computed(() => currentState.value?.answers)
const currentField = computed(() => props.fields[currentIndex.value] ?? {})
const currentProfile = computed(() => currentState.value?.profile)

const historyPending = computed(() => ['loading', 'partial'].includes(currentState.value?.historyStatus))
const estimatedYears = computed(() => (currentAnswers.value?.cropHistory || []).filter((entry) => entry.estimate).length)
const historyChip = computed(() => ({
  loading: 'Checking…',
  partial: 'Partly loaded',
  complete: 'Loaded',
}[currentState.value?.historyStatus] || 'Manual entry'))
const historyMessage = computed(() => {
  const state = currentState.value
  if (!state) return ''
  switch (state.historyStatus) {
    case 'loading':
      return 'Looking up this field in the satellite crop record. This can take a minute or more — you can pick crops yourself in the meantime.'
    case 'partial':
      return `Found ${estimatedYears.value} of ${years.length} years so far, still checking the rest. Anything you pick yourself is kept.`
    case 'complete':
      return `Satellite estimates loaded for ${estimatedYears.value} of ${years.length} years. Please check each year and correct anything that is wrong.`
    case 'timeout':
      return `The satellite record is taking too long (${estimatedYears.value} of ${years.length} years found). Please fill in the rest yourself.`
    case 'error':
      return `Could not load the satellite crop record (${state.historyNote}). Please enter the crop history yourself.`
    default:
      return state.historyNote || 'No satellite crop record for this field. Please enter the crop history yourself.'
  }
})

function agreementText(confidence) {
  if (confidence == null) return ''
  return confidence >= 0.995
    ? ' · all sampled points agree'
    : ` · ${Math.round(confidence * 100)}% of sampled points agree`
}

function entryLabel(entry) {
  if (entry.source === 'farmer') {
    return entry.estimate ? `Your choice · satellite saw ${entry.estimate.crop_label}` : 'Your choice'
  }
  if (entry.estimate) {
    const unmapped = entry.estimate.crop_id ? '' : ' — not in our crop list, pick the closest'
    return `Satellite saw ${entry.estimate.crop_label}${agreementText(entry.estimate.confidence)}${unmapped}`
  }
  return historyPending.value ? 'Checking satellite record…' : 'No satellite estimate'
}

const fieldNumber = computed(() => currentIndex.value + 1)
const acres = computed(() => {
  const boundary = currentField.value.boundary ?? []
  if (boundary.length < 3) return 0

  const earthRadiusMeters = 6378137
  let area = 0
  for (let index = 0; index < boundary.length; index += 1) {
    const current = boundary[index]
    const next = boundary[(index + 1) % boundary.length]
    const currentLatitude = current.lat * Math.PI / 180
    const nextLatitude = next.lat * Math.PI / 180
    const longitudeDifference = (next.lng - current.lng) * Math.PI / 180
    area += longitudeDifference * (2 + Math.sin(currentLatitude) + Math.sin(nextLatitude))
  }

  const squareMeters = Math.abs(area * earthRadiusMeters * earthRadiusMeters / 2)
  return squareMeters / 4046.8564224
})

const formattedAcres = computed(() => new Intl.NumberFormat(undefined, {
  maximumFractionDigits: 2,
  minimumFractionDigits: 2,
}).format(acres.value))

function showNextField() {
  if (currentIndex.value < props.fields.length - 1) currentIndex.value += 1
}

function showPreviousField() {
  if (currentIndex.value > 0) currentIndex.value -= 1
}

function updateCropEntry(entry) {
  const crop = cropOptions.value.find((option) => option.id === entry.crop_id)
  entry.crop_label = crop?.name || 'Unknown'
  entry.source = 'farmer'
  entry.confidence = null
}

function continueWithConfirmedHistory() {
  emit('continue', {
    profiles: fieldStates.value.map((state) => state.profile),
    answers: fieldStates.value.map(({ answers }) => ({
      ...answers,
      cropHistory: answers.cropHistory.map((entry) => ({
        year: entry.year,
        crop_id: entry.crop_id || null,
        crop_label: entry.crop_label,
        confidence: entry.source === 'farmer' ? null : entry.confidence,
        source: entry.source,
      })),
    })),
  })
}
</script>

<template>
  <main class="page-shell">
    <header class="brand" aria-label="Patato">
      <span class="brand-mark" aria-hidden="true">
        <svg viewBox="0 0 40 40" fill="none">
          <path d="M8 23c0-8 6-13.5 14.5-13 7 .5 12 5 12 11.5 0 7.5-6.5 12.5-15 12.5C13 34 8 29.5 8 23Z" />
          <path d="M15 21.5q2-2 4 0" />
          <path d="M24 18.5q2-2 4 0" />
          <path d="M21.5 27q2-2 4 0" />
        </svg>
      </span>
      <span>Patato</span>
    </header>

    <section v-if="currentState" class="field-info-page" aria-labelledby="field-info-title">
      <div class="field-info-header">
        <button class="back-button" type="button" @click="emit('go-back')">
          <span aria-hidden="true">←</span> Back to fields
        </button>
        <p class="field-progress">Field {{ fieldNumber }} of {{ fields.length }}</p>
      </div>

      <div class="field-info-intro">
        <p class="eyebrow">{{ currentField.name || `Field ${fieldNumber}` }}</p>
        <h1 id="field-info-title">Field information</h1>
        <p>Review this field’s size, water access, and recent crop history.</p>
      </div>

      <div class="field-info-sections">
        <section class="field-info-card area-card" aria-labelledby="area-title">
          <div>
            <p class="field-card-eyebrow">Calculated from your map outline</p>
            <h2 id="area-title">Field size</h2>
          </div>
          <p class="area-value"><strong>{{ formattedAcres }}</strong><span>acres</span></p>
        </section>

        <section v-if="currentState.profileStatus === 'loading'" class="field-info-card" aria-labelledby="profile-loading-title">
          <h2 id="profile-loading-title">What we found</h2>
          <p class="history-status" role="status">
            <span class="inline-spinner" aria-hidden="true"></span>
            <span>Loading soil and climate data for this field…</span>
          </p>
        </section>

        <section v-else-if="currentProfile" class="field-info-card" aria-labelledby="profile-title">
          <h2 id="profile-title">What we found</h2>
          <p v-if="currentProfile.soil?.name || currentProfile.soil?.texture_class">
            Soil: {{ currentProfile.soil.name || currentProfile.soil.texture_class }}
            <span v-if="currentProfile.soil.ph != null"> · pH {{ currentProfile.soil.ph }}</span>
          </p>
          <p v-if="currentProfile.climate">
            Recent climate ({{ currentProfile.climate.recent.years }}):
            {{ Math.round(currentProfile.climate.recent.precip_season_mm) }} mm growing-season rain
          </p>
          <p class="field-card-help">Data sources: {{ currentProfile.sources.join(', ') }}</p>
          <p v-for="gap in currentProfile.gaps" :key="gap" class="field-card-help">{{ gap }}</p>
        </section>

        <section class="field-info-card" aria-labelledby="water-title">
          <h2 id="water-title"><span class="section-icon" aria-hidden="true">💧</span>Water for this field</h2>
          <p v-if="currentProfile?.water_use?.available" class="field-card-help">🛰️ {{ currentProfile.water_use.note }}</p>
          <label class="resource-question-label" :for="`irrigated-${fieldNumber}`">Is this field irrigated?</label>
          <select :id="`irrigated-${fieldNumber}`" v-model="currentAnswers.irrigated" @change="currentAnswers.waterTouched = true">
            <option value="">Not sure</option>
            <option value="yes">Yes</option>
            <option value="no">No — rain only</option>
          </select>
          <template v-if="currentAnswers.irrigated === 'yes'">
            <label class="resource-question-label" :for="`irrigation-method-${fieldNumber}`">How is it irrigated?</label>
            <select :id="`irrigation-method-${fieldNumber}`" v-model="currentAnswers.irrigationMethod" @change="currentAnswers.waterTouched = true">
              <option value="" disabled>Choose a method</option>
              <option value="drip">Drip</option>
              <option value="sprinkler">Sprinkler or pivot</option>
              <option value="surface">Flood or furrow</option>
            </select>
            <label class="resource-question-label" :for="`water-source-${fieldNumber}`">Where does the water come from?</label>
            <select :id="`water-source-${fieldNumber}`" v-model="currentAnswers.waterSource" @change="currentAnswers.waterTouched = true">
              <option value="" disabled>Choose a source</option>
              <option value="surface">Canal or river</option>
              <option value="groundwater">Well</option>
              <option value="mixed">Both</option>
            </select>
          </template>
        </section>

        <section class="field-info-card" aria-labelledby="history-title">
          <div class="history-heading">
            <div>
              <h2 id="history-title"><span class="section-icon" aria-hidden="true">🌱</span>Crop history</h2>
              <p class="field-card-help">
                Where we can, we fill in what USDA’s satellite crop map saw at sample points inside your field.
                You know your field best — check each year and change anything that is wrong.
              </p>
            </div>
            <span class="sample-badge" :class="{ 'sample-badge-pending': historyPending }">{{ historyChip }}</span>
          </div>
          <p
            class="history-status"
            :class="{ 'history-status-problem': ['error', 'timeout'].includes(currentState.historyStatus) }"
            role="status"
            aria-live="polite"
          >
            <span v-if="historyPending" class="inline-spinner" aria-hidden="true"></span>
            <span>{{ historyMessage }}</span>
          </p>
          <p v-if="currentState.historySource" class="field-card-help">Source: {{ currentState.historySource }}</p>
          <p v-if="catalogStatus === 'loading'" class="field-card-help" role="status">Loading the crop list…</p>
          <p v-else-if="catalogStatus === 'error'" class="field-card-help" role="alert">
            Could not load the crop list.
            <button class="cancel-outline-button" type="button" @click="loadCatalog">Try again</button>
          </p>
          <div class="crop-history-list">
            <label v-for="(entry, index) in currentAnswers.cropHistory" :key="entry.year" class="crop-year">
              <span>{{ entry.year }}</span>
              <select :id="`field-${fieldNumber}-crop-${entry.year}`" v-model="entry.crop_id" @change="updateCropEntry(entry)">
                <option value="">Unknown / not sure</option>
                <option v-for="crop in cropOptions" :key="crop.id" :value="crop.id">{{ crop.name }}</option>
              </select>
              <small class="history-source-label">
                <span v-if="historyPending && !entry.estimate && entry.source !== 'farmer'" class="inline-spinner inline-spinner-small" aria-hidden="true"></span>
                {{ entryLabel(entry) }}
              </small>
            </label>
          </div>
        </section>
      </div>

      <div class="field-info-actions">
        <button v-if="currentIndex > 0" class="secondary-button" type="button" @click="showPreviousField">
          <span aria-hidden="true">←</span> Previous field
        </button>
        <span v-else></span>
        <button
          v-if="currentIndex < fields.length - 1"
          class="primary-button"
          type="button"
          @click="showNextField"
        >
          Next field <span aria-hidden="true">→</span>
        </button>
        <button v-else class="primary-button" type="button" @click="continueWithConfirmedHistory">
          Continue to resources <span aria-hidden="true">→</span>
        </button>
      </div>
    </section>
  </main>
</template>
