<script setup>
import { computed, ref, watch } from 'vue'
import ResourceQuestion from './ResourceQuestion.vue'
import { getCatalog, getFieldProfile } from '../api.js'

const props = defineProps({
  fields: { type: Array, required: true },
})
const emit = defineEmits(['go-back', 'continue'])

const years = [2021, 2022, 2023, 2024, 2025]
const cropOptions = ref([])
const profiles = ref([])
const profileLoading = ref(false)
const profileError = ref('')

const currentIndex = ref(0)
const fieldAnswers = ref([])

function normalizeCropId(id) {
  return id === 'maize' ? 'corn_silage' : id
}

watch(() => props.fields, async (fields) => {
  currentIndex.value = 0
  profileLoading.value = true
  profileError.value = ''
  fieldAnswers.value = fields.map(() => ({
    waterSources: [],
    waterSourcesOther: '',
    irrigationMethods: [],
    irrigationOther: '',
    cropHistory: years.map((year) => ({ year, crop_id: null, crop_label: 'Unknown', confidence: null, source: 'unknown' })),
  }))
  try {
    const [catalog, fieldProfiles] = await Promise.all([
      getCatalog(),
      Promise.all(fields.map((field) => getFieldProfile(field))),
    ])
    cropOptions.value = catalog
    profiles.value = fieldProfiles
    fieldAnswers.value = fields.map((_, index) => {
      const automatic = new Map((fieldProfiles[index].crop_history?.years || []).map((entry) => [entry.year, entry]))
      return {
        ...fieldAnswers.value[index],
        cropHistory: years.map((year) => {
          const found = automatic.get(year)
            return found
              ? { ...found, crop_id: normalizeCropId(found.crop_id) || null }
            : { year, crop_id: null, crop_label: 'Unknown', confidence: null, source: 'unknown' }
        }),
      }
    })
  } catch (error) {
    profileError.value = error.message || 'Could not load field information.'
  } finally {
    profileLoading.value = false
  }
}, { immediate: true })

const currentAnswers = computed(() => fieldAnswers.value[currentIndex.value])
const currentField = computed(() => props.fields[currentIndex.value] ?? {})
const currentProfile = computed(() => profiles.value[currentIndex.value])
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
  const crop = cropOptions.value.find((option) => option.id === normalizeCropId(entry.crop_id))
  entry.crop_id = normalizeCropId(entry.crop_id)
  entry.crop_label = crop?.name || 'Unknown'
  entry.source = 'farmer'
  entry.confidence = null
}

function continueWithConfirmedHistory() {
  emit('continue', {
    profiles: profiles.value,
    answers: fieldAnswers.value.map((answer) => ({
      ...answer,
      cropHistory: answer.cropHistory.map((entry) => ({
        year: entry.year,
        crop_id: entry.crop_id || null,
        crop_label: entry.crop_label,
        confidence: entry.source === 'farmer' ? null : entry.confidence,
        source: entry.source === 'unknown' ? 'unknown' : entry.source,
      })),
    })),
  })
}
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

    <section class="field-info-page" aria-labelledby="field-info-title">
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

        <section v-if="currentProfile" class="field-info-card" aria-labelledby="profile-title">
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
          <p class="field-card-help">Choose what is available at this field.</p>
          <ResourceQuestion
            v-model="currentAnswers.waterSources"
            v-model:other-detail="currentAnswers.waterSourcesOther"
            id="field-water-sources"
            label="What are this field’s primary water sources?"
            :options="['Well', 'River / Stream', 'Pond / Lake', 'Municipal water', 'Rainwater', 'Other', 'No reliable water source']"
            exclusive-option="No reliable water source"
          />
          <ResourceQuestion
            v-model="currentAnswers.irrigationMethods"
            v-model:other-detail="currentAnswers.irrigationOther"
            id="field-irrigation-methods"
            label="What irrigation methods are available for this field?"
            :options="['Drip irrigation', 'Sprinkler', 'Flood irrigation', 'Other', 'None']"
            exclusive-option="None"
          />
        </section>

        <section class="field-info-card" aria-labelledby="history-title">
          <div class="history-heading">
            <div>
              <h2 id="history-title"><span class="section-icon" aria-hidden="true">🌱</span>Crop history</h2>
              <p class="field-card-help">Space-based estimates are shown when available. Please check and correct each year.</p>
            </div>
            <span class="sample-badge">{{ currentProfile?.crop_history?.source || 'Field history' }}</span>
          </div>
          <p v-if="profileLoading" class="field-card-help" role="status">Loading field data and crop history. This can take up to a minute.</p>
          <p v-else-if="profileError" class="field-card-help" role="alert">{{ profileError }} You can still enter crop history manually.</p>
          <p v-else-if="currentProfile?.crop_history?.note" class="field-card-help">{{ currentProfile.crop_history.note }}</p>
          <div class="crop-history-list">
            <label v-for="(entry, index) in currentAnswers.cropHistory" :key="entry.year" class="crop-year">
              <span>{{ entry.year }}</span>
              <select :id="`field-${fieldNumber}-crop-${entry.year}`" v-model="entry.crop_id" @change="updateCropEntry(entry)">
                <option value="">Unknown / not sure</option>
                <option v-for="crop in cropOptions" :key="crop.id" :value="crop.id">{{ crop.name }}</option>
              </select>
              <small class="history-source-label">
                {{ entry.source === 'farmer' ? 'Your correction' : entry.source === 'cdl' && entry.confidence != null ? `Estimate · ${Math.round(entry.confidence * 100)}% agreement` : 'No estimate available' }}
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
        <button v-else class="primary-button" type="button" :disabled="profileLoading" @click="continueWithConfirmedHistory">
          Continue to resources <span aria-hidden="true">→</span>
        </button>
      </div>
    </section>
  </main>
</template>
