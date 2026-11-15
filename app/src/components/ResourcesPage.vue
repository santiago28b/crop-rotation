<script setup>
import { reactive, ref, watch } from 'vue'
import ResourceQuestion from './ResourceQuestion.vue'
import { getInsights, getProfitReport, getReportCrops } from '../api.js'
import { reportCropId } from '../results.js'

const props = defineProps({
  fields: { type: Array, default: () => [] },
  profiles: { type: Array, default: () => [] },
  fieldAnswers: { type: Array, default: () => [] },
})
const emit = defineEmits(['go-back', 'recommendations-started', 'recommendations-ready', 'recommendations-error'])
const saved = ref(false)
const sending = ref(false)
const results = ref([])
const requestError = ref('')
// The crops the money comparison knows. Built in, so the "what is growing now?" list
// works instantly and even when the API is slow or down; refreshed from GET /crops.
const BUILT_IN_CROPS = [
  { crop: 'alfalfa', label: 'Alfalfa hay' },
  { crop: 'corn_silage', label: 'Corn silage' },
  { crop: 'winter_wheat', label: 'Winter wheat' },
  { crop: 'spring_barley', label: 'Spring barley' },
  { crop: 'sugar_beets', label: 'Sugar beets' },
  { crop: 'onions', label: 'Onions' },
  { crop: 'dry_beans', label: 'Dry beans' },
  { crop: 'potatoes', label: 'Potatoes' },
  { crop: 'mint', label: 'Mint (oil)' },
]
const reportCrops = ref(BUILT_IN_CROPS)
const currentCrops = ref([])
const waterSupplies = ref([])
const priorities = reactive({ water: 0.5, soil_health: 0.5, income: 0.5, low_risk: 0.5 })
const priorityQuestions = [
  { key: 'water', label: 'Using less water' },
  { key: 'soil_health', label: 'Building soil health' },
  { key: 'income', label: 'Income potential' },
  { key: 'low_risk', label: 'Lower risk' },
]

function initialCrop(answer) {
  const known = [...(answer?.cropHistory || [])].reverse().find((entry) =>
    reportCrops.value.some((crop) => crop.crop === reportCropId(entry.crop_id)))
  return reportCropId(known?.crop_id) || ''
}

watch(() => props.fields, (fields) => {
  currentCrops.value = fields.map((_, index) => initialCrop(props.fieldAnswers[index]))
  waterSupplies.value = fields.map(() => 'limited')
  results.value = fields.map(() => null)
}, { immediate: true })

// Refresh the list in the background; the built-in one is already usable.
getReportCrops().then((crops) => {
  if (Array.isArray(crops) && crops.length) reportCrops.value = crops
}).catch(() => {})

// Only question either engine actually uses: what can you harvest with?
const HARVESTER_CLASSES = {
  'Combine (grain)': 'grain_combine',
  'Forage or silage harvester': 'forage_harvester',
  'Root crop harvester (beets, potatoes)': 'root_harvester',
}
const harvesterAnswers = ref([])

watch([harvesterAnswers, currentCrops, waterSupplies], () => {
  saved.value = false
}, { deep: true })

function buildInsightsResources(answer, index) {
  const irrigated = answer?.irrigated === 'yes'
  return {
    irrigation: {
      type: irrigated ? (answer.irrigationMethod || 'sprinkler') : 'none',
      seasonal_allotment_mm: null,
      supply: waterSupplies.value[index] || 'limited',
    },
    harvesters: harvesterAnswers.value
      .map((label) => HARVESTER_CLASSES[label])
      .filter(Boolean),
    planters: [],
    labor: null,
  }
}

async function saveResources() {
  sending.value = true
  saved.value = false
  requestError.value = ''
  results.value = props.fields.map(() => null)
  emit('recommendations-started', { fields: props.fields })
  const output = await Promise.all(props.fields.map(async (field, index) => {
    const answer = props.fieldAnswers[index] || {}
    const current = currentCrops.value[index]
    // Farmer-confirmed history, real ids (maize stays maize for the agronomy engine)
    const history = (answer.cropHistory || []).filter((entry) => entry.crop_id).map((entry) => ({
      year: entry.year,
      crop_id: entry.crop_id,
      crop_label: entry.crop_label || 'Unknown',
      confidence: entry.source === 'farmer' ? null : entry.confidence,
      source: entry.source || 'unknown',
    }))
    if (current) {
      history.push({ year: 2026, crop_id: current, crop_label: cropName(current), confidence: null, source: 'farmer' })
    }

    // Agronomy first: its viable candidates narrow the money comparison
    let insights = null
    let insightsError = ''
    try {
      insights = await getInsights(field, history, buildInsightsResources(answer, index), { ...priorities })
    } catch (error) {
      insightsError = error.message || 'The field analysis failed.'
    }

    let areaCrops = (insights?.candidates || [])
      .map((candidate) => reportCropId(candidate.crop_id))
      .filter((id, i, all) => all.indexOf(id) === i)
      .filter((id) => reportCrops.value.some((crop) => crop.crop === id))
      .map((crop) => ({ crop }))
    if (!areaCrops.length) {
      areaCrops = [...new Set(history.map((entry) => reportCropId(entry.crop_id)))]
        .filter((id) => reportCrops.value.some((crop) => crop.crop === id))
        .map((crop) => ({ crop }))
    }

    // Water needs computed for this location (FAO-56); /report uses them outside SW Idaho
    const waterNeeds = Object.fromEntries((insights?.candidates || [])
      .filter((candidate) => candidate.water?.crop_need_mm > 0)
      .map((candidate) => [reportCropId(candidate.crop_id), Math.round(candidate.water.crop_need_mm / 25.4 * 10) / 10]))

    let report = null
    let reportError = ''
    if (current) {
      try {
        report = await getProfitReport(
          field, current, waterSupplies.value[index], areaCrops,
          answer.irrigated === 'yes' ? (answer.irrigationMethod || 'sprinkler')
            : answer.irrigated === 'no' ? 'none' : undefined,
          answer.irrigated === 'yes' ? (answer.waterSource || 'surface') : undefined,
          waterNeeds,
        )
      } catch (error) {
        reportError = error.message || 'The profit comparison failed.'
      }
    }
    return { insights, insightsError, report, reportError }
  }))
  results.value = output
  saved.value = output.some((result) => result.insights || result.report)
  if (!saved.value) {
    requestError.value = output[0]?.insightsError || output[0]?.reportError || 'Could not get crop recommendations.'
    emit('recommendations-error', requestError.value)
  }
  sending.value = false
  emit('recommendations-ready', { fields: props.fields, results: output })
}

function cropName(id) {
  return reportCrops.value.find((crop) => crop.crop === id)?.label || id
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

    <section class="resources-page" aria-labelledby="resources-title">
      <div class="resources-header">
        <button class="back-button" type="button" @click="emit('go-back')">
          <span aria-hidden="true">←</span> Back to field details
        </button>
      </div>

      <div class="resources-intro">
        <p class="eyebrow">Your farm</p>
        <h1 id="resources-title">Almost there</h1>
        <p>A few last questions, then we compare crops for every field.</p>
      </div>

      <form class="resources-form" @submit.prevent="saveResources">
        <section v-for="(field, index) in fields" :key="`comparison-${index}`" class="resource-section comparison-inputs">
          <h2>{{ field.name || `Field ${index + 1}` }}</h2>
          <div class="form-field">
            <label class="resource-question-label" :for="`current-crop-${index}`">What crop is growing here now?</label>
            <select :id="`current-crop-${index}`" v-model="currentCrops[index]" class="form-select" required>
              <option value="" disabled>Choose a crop</option>
              <option v-for="crop in reportCrops" :key="crop.crop" :value="crop.crop">{{ crop.label }}</option>
            </select>
          </div>
          <div class="form-field">
            <label class="resource-question-label" :for="`water-supply-${index}`">How reliable is the water supply?</label>
            <select :id="`water-supply-${index}`" v-model="waterSupplies[index]" class="form-select">
              <option value="full">Reliable / full supply</option>
              <option value="limited">Some limits</option>
              <option value="short">Short or unreliable</option>
            </select>
          </div>
        </section>

        <section class="resource-section">
          <h2><span class="section-icon" aria-hidden="true">🛠️</span>Harvest equipment</h2>
          <ResourceQuestion
            v-model="harvesterAnswers"
            id="harvesters"
            label="What harvest equipment do you have access to?"
            :options="['Combine (grain)', 'Forage or silage harvester', 'Root crop harvester (beets, potatoes)', 'Not sure']"
            exclusive-option="Not sure"
            :multiple="true"
          />
        </section>

        <section class="resource-section priority-section">
          <h2>What matters most when choosing crops?</h2>
          <p class="field-card-help">Choose “Equal” if you do not have a strong preference.</p>
          <label v-for="priority in priorityQuestions" :key="priority.key" class="priority-row" :for="`priority-${priority.key}`">
            <span>{{ priority.label }}</span>
            <select :id="`priority-${priority.key}`" v-model.number="priorities[priority.key]" class="form-select">
              <option :value="0.25">Less important</option>
              <option :value="0.5">Equal</option>
              <option :value="1">More important</option>
            </select>
          </label>
        </section>

        <div class="resource-submit-row">
          <p v-if="saved" class="resource-saved" role="status">Recommendations are ready.</p>
          <button class="primary-button" type="submit" :disabled="sending">
            {{ sending ? 'Working on your recommendations…' : saved ? 'Update recommendations' : 'Get crop recommendations' }}
            <span aria-hidden="true">✓</span>
          </button>
        </div>
      </form>
      <p v-if="requestError" class="api-error" role="alert">{{ requestError }}</p>

    </section>
  </main>
</template>
