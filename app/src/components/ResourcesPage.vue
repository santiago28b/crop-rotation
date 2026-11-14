<script setup>
import { reactive, ref, watch } from 'vue'
import ResourceQuestion from './ResourceQuestion.vue'
import { getInsights, getProfitReport, getReportCrops } from '../api.js'

const props = defineProps({
  fields: { type: Array, default: () => [] },
  profiles: { type: Array, default: () => [] },
  fieldAnswers: { type: Array, default: () => [] },
})
const emit = defineEmits(['go-back'])
const saved = ref(false)
const sending = ref(false)
const results = ref([])
const requestError = ref('')
const reportCrops = ref([])
const currentCrops = ref([])
const waterSupplies = ref([])
const priorities = reactive({ water: 0.5, soil_health: 0.5, income: 0.5, low_risk: 0.5 })
const priorityQuestions = [
  { key: 'water', label: 'Using less water' },
  { key: 'soil_health', label: 'Building soil health' },
  { key: 'income', label: 'Income potential' },
  { key: 'low_risk', label: 'Lower risk' },
]

// The economics engine models silage corn; CDL/insights call grain corn "maize".
// This mapping lives only at the /report boundary — insights gets the real ids.
function reportCropId(id) {
  return id === 'maize' ? 'corn_silage' : id
}

function initialCrop(answer) {
  const known = [...(answer?.cropHistory || [])].reverse().find((entry) =>
    reportCrops.value.some((crop) => crop.crop === reportCropId(entry.crop_id)))
  return reportCropId(known?.crop_id) || ''
}

watch(() => props.fields, async (fields) => {
  try {
    reportCrops.value = await getReportCrops()
  } catch (error) {
    requestError.value = `Could not load the profit comparison crop list: ${error.message}`
  }
  currentCrops.value = fields.map((_, index) => initialCrop(props.fieldAnswers[index]))
  waterSupplies.value = fields.map(() => 'limited')
  results.value = fields.map(() => null)
}, { immediate: true })

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

    let report = null
    let reportError = ''
    if (current) {
      try {
        report = await getProfitReport(
          field, current, waterSupplies.value[index], areaCrops,
          answer.irrigated === 'yes' ? (answer.irrigationMethod || 'sprinkler')
            : answer.irrigated === 'no' ? 'none' : undefined,
          answer.irrigated === 'yes' ? (answer.waterSource || 'surface') : undefined,
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
  }
  sending.value = false
}

function formatMoney(value) {
  if (value == null) return 'Not available'
  return new Intl.NumberFormat(undefined, { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(value)
}

function formatPercent(value) {
  return value == null ? '—' : `${Math.round(value * 100)}%`
}

function cropName(id) {
  return reportCrops.value.find((crop) => crop.crop === id)?.label || id
}

function doyToDate(doy) {
  if (doy == null) return ''
  return new Date(Date.UTC(2026, 0, doy)).toLocaleDateString('en-US', { month: 'short', day: 'numeric', timeZone: 'UTC' })
}

const TAG_LABELS = {
  current: 'Your current crop',
  best_overall: 'Best overall',
  safest_dry_year: 'Safest in a dry year',
  best_for_soil: 'Best for the soil',
  alternative: 'Also worth a look',
}

// One row per money option, joined with its agronomy candidate by crop id
function mergedOptions(result) {
  const candidates = new Map((result.insights?.candidates || [])
    .map((candidate) => [reportCropId(candidate.crop_id), candidate]))
  return (result.report?.options || []).map((option) => ({
    option,
    candidate: candidates.get(option.crop) || null,
  }))
}

// Agronomy-only candidates the economics table has no numbers for
function extraCandidates(result) {
  const inReport = new Set((result.report?.options || []).map((option) => option.crop))
  return (result.insights?.candidates || [])
    .filter((candidate) => !inReport.has(reportCropId(candidate.crop_id)))
    .slice(0, 5)
}

function dataNotesText(option) {
  const notes = option.data_notes
  if (!notes || typeof notes !== 'object') return ''
  return Object.entries(notes).map(([key, value]) => `${key.replaceAll('_', ' ')}: ${value}`).join(' · ')
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
          <label class="resource-question-label" :for="`current-crop-${index}`">What crop is growing here now?</label>
          <select :id="`current-crop-${index}`" v-model="currentCrops[index]">
            <option value="" disabled>Choose a crop</option>
            <option v-for="crop in reportCrops" :key="crop.crop" :value="crop.crop">{{ crop.label }}</option>
          </select>
          <label class="resource-question-label" :for="`water-supply-${index}`">How reliable is the water supply?</label>
          <select :id="`water-supply-${index}`" v-model="waterSupplies[index]">
            <option value="full">Reliable / full supply</option>
            <option value="limited">Some limits</option>
            <option value="short">Short or unreliable</option>
          </select>
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
            <select :id="`priority-${priority.key}`" v-model.number="priorities[priority.key]">
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

      <template v-for="(result, index) in results" :key="`results-${index}`">
        <section v-if="result" class="recommendations-result">
          <p class="eyebrow">{{ fields[index]?.name || `Field ${index + 1}` }}</p>
          <h2>Crop options for this field</h2>

          <p v-if="result.report?.region_warning" class="api-error">{{ result.report.region_warning }}</p>
          <p v-if="result.report?.summary" class="result-summary">{{ result.report.summary }}</p>
          <p v-if="result.report?.year_odds" class="field-card-help">
            Next-season outlook: dry {{ formatPercent(result.report.year_odds.dry) }} ·
            normal {{ formatPercent(result.report.year_odds.normal) }} ·
            wet {{ formatPercent(result.report.year_odds.wet) }}
            <span v-if="result.report?.snowpack?.note"> — {{ result.report.snowpack.note }}</span>
          </p>
          <div v-if="result.report?.field_water_use?.season_et_in != null" class="field-water-use">
            <p>🛰️ {{ result.report.field_water_use.note }}</p>
            <small>{{ result.report.field_water_use.source }}</small>
          </div>

          <p v-if="result.insightsError" class="api-error">Field analysis unavailable: {{ result.insightsError }}</p>
          <p v-if="result.reportError" class="api-error">Profit comparison unavailable: {{ result.reportError }}</p>
          <p v-if="!result.report && !result.reportError" class="field-card-help">Choose a current crop above to see the profit comparison.</p>

          <article v-for="{ option, candidate } in mergedOptions(result)" :key="option.crop" class="recommendation-card">
            <h4>{{ option.label || cropName(option.crop) }} <small>· {{ TAG_LABELS[option.tag] || option.tag.replaceAll('_', ' ') }}</small></h4>
            <p>
              <strong>{{ formatMoney(option.expected_profit_per_acre) }}/acre expected</strong>
              · {{ formatMoney(option.dry_year_profit_per_acre) }}/acre in a dry year
              · {{ formatMoney(option.expected_profit_field) }} for this field
            </p>
            <p v-if="option.why">{{ option.why }}</p>
            <p v-if="candidate" class="field-card-help">
              Growing fit {{ Math.round(candidate.suitability?.overall != null ? candidate.suitability.overall * 100 : candidate.score * 100) }}%
              <span v-if="candidate.plant_window"> · plant {{ doyToDate(candidate.plant_window.start_doy) }}–{{ doyToDate(candidate.plant_window.end_doy) }}</span>
              <span v-if="candidate.water?.crop_need_mm != null"> · needs about {{ Math.round(candidate.water.crop_need_mm / 25.4) }} in of water</span>
              <span v-if="candidate.rotation?.flags?.length"> · {{ candidate.rotation.flags.join('; ') }}</span>
            </p>
            <p v-if="option.risks?.length" class="field-card-help">⚠ {{ option.risks[0] }}</p>
            <small v-if="dataNotesText(option)" class="field-card-help">{{ dataNotesText(option) }}</small>
          </article>

          <p v-if="extraCandidates(result).length" class="field-card-help">
            Also fits here agronomically (no local price data yet):
            {{ extraCandidates(result).map((candidate) => candidate.name).join(', ') }}
          </p>

          <details v-if="result.report || result.insights">
            <summary>Data and assumptions</summary>
            <p v-if="result.report?.disclaimer">{{ result.report.disclaimer }}</p>
            <p>Data sources: {{ [...(result.report?.data_sources || []), ...(result.insights?.sources || [])].join(', ') }}</p>
          </details>
        </section>
      </template>
    </section>
  </main>
</template>
