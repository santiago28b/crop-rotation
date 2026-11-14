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

const sections = [
  {
    title: 'Equipment',
    icon: '🛠️',
    questions: [
      {
        id: 'equipment',
        label: '1. What equipment do you have access to?',
        options: ['Tractor', 'Plow / Tiller', 'Seeder / Planter', 'Harvester', 'Sprayer', 'Trailer / Truck', 'Hand tools', 'Other', 'None'],
        exclusiveOption: 'None',
        multiple: true,
        otherKey: 'equipmentOther',
      },
      {
        id: 'equipmentCondition',
        label: '2. What is the general condition of your equipment?',
        options: ['Good condition', 'Some needs repairs', 'Most needs repairs', 'Not applicable'],
        multiple: false,
      },
    ],
  },
  {
    title: 'Labor',
    icon: '👥',
    questions: [
      {
        id: 'availableWorkers',
        label: '3. How many people are available to work on your farm?',
        options: ['1', '2–5', '6–10', '11–20', 'More than 20'],
        multiple: false,
      },
      {
        id: 'seasonalWorkers',
        label: '4. Do you have access to additional seasonal workers?',
        options: ['Yes', 'No', 'Sometimes'],
        multiple: false,
      },
    ],
  },
  {
    title: 'Facilities',
    icon: '🏠',
    questions: [
      {
        id: 'facilities',
        label: '5. What facilities do you have?',
        options: ['Barn', 'Storage building', 'Greenhouse', 'Workshop', 'Livestock facilities', 'Fencing', 'None', 'Other'],
        exclusiveOption: 'None',
        multiple: true,
        otherKey: 'facilitiesOther',
      },
    ],
  },
  {
    title: 'Supplies',
    icon: '📦',
    questions: [
      {
        id: 'supplies',
        label: '6. What supplies do you currently have available?',
        options: ['Seeds', 'Fertilizer', 'Compost', 'Pesticides / Herbicides', 'Animal feed', 'Fuel', 'Other', 'None'],
        exclusiveOption: 'None',
        multiple: true,
        otherKey: 'suppliesOther',
      },
    ],
  },
  {
    title: 'Additional Resources',
    icon: '🌱',
    questions: [
      {
        id: 'additionalResources',
        label: '7. What other resources do you have access to?',
        options: ['Transportation', 'Electricity', 'Internet', 'Agricultural cooperatives', 'Shared equipment with other farmers', 'Community farming organizations', 'Other'],
        multiple: true,
        otherKey: 'additionalResourcesOther',
      },
      {
        id: 'biggestNeed',
        label: '8. What is the biggest resource your farm currently lacks?',
        options: ['Water', 'Equipment', 'Labor', 'Land', 'Supplies', 'Infrastructure', 'Funding', 'Other'],
        multiple: false,
        otherKey: 'biggestNeedOther',
      },
    ],
  },
]

const answers = reactive(Object.fromEntries(
  sections.flatMap((section) => section.questions.map((question) => [
    question.id,
    question.multiple ? [] : '',
  ])),
))

const otherDetails = reactive(Object.fromEntries(
  sections.flatMap((section) => section.questions
    .filter((question) => question.otherKey)
    .map((question) => [question.id, ''])),
))

watch([answers, otherDetails], () => {
  saved.value = false
})

function buildInsightsResources(fieldAnswers) {
  const methods = (fieldAnswers?.irrigationMethods || []).map((value) => value.toLowerCase())
  const irrigationType = methods.some((value) => value.includes('drip')) ? 'drip'
    : methods.some((value) => value.includes('sprinkler')) ? 'sprinkler'
      : methods.some((value) => value.includes('flood')) ? 'surface' : 'none'
  const equipment = answers.equipment || []
  const labor = answers.availableWorkers === '1' || answers.availableWorkers === '2–5' ? 'low'
    : answers.availableWorkers === '6–10' ? 'medium'
      : answers.availableWorkers ? 'high' : null
  return {
    irrigation: { type: irrigationType, seasonal_allotment_mm: null },
    harvesters: equipment.some((item) => /harvest/i.test(item)) ? ['manual'] : [],
    planters: equipment.some((item) => /seeder|planter/i.test(item)) ? ['manual'] : [],
    labor,
  }
}

async function saveResources() {
  sending.value = true
  saved.value = false
  requestError.value = ''
  results.value = props.fields.map(() => null)
  try {
    const output = await Promise.all(props.fields.map(async (field, index) => {
      const answer = props.fieldAnswers[index] || {}
      const history = (answer.cropHistory || []).map((entry) => ({
        year: entry.year,
        crop_id: entry.crop_id || null,
        crop_label: entry.crop_label || 'Unknown',
        confidence: entry.source === 'farmer' ? null : entry.confidence,
        source: entry.source || 'unknown',
      }))
      const reportHistory = [...new Set(history.map((entry) => reportCropId(entry.crop_id)))]
        .filter((id) => reportCrops.value.some((crop) => crop.crop === id))
        .map((crop) => ({ crop }))
      const [insights, report] = await Promise.all([
        getInsights(field, history, buildInsightsResources(answer), { ...priorities }),
        currentCrops.value[index]
          ? getProfitReport(field, currentCrops.value[index], waterSupplies.value[index], reportHistory)
          : Promise.resolve(null),
      ])
      return { insights, report }
    }))
    results.value = output
    saved.value = true
  } catch (error) {
    requestError.value = error.message || 'Could not get crop recommendations.'
  } finally {
    sending.value = false
  }
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

    <section class="resources-page" aria-labelledby="resources-title">
      <div class="resources-header">
        <button class="back-button" type="button" @click="emit('go-back')">
          <span aria-hidden="true">←</span> Back to field details
        </button>
      </div>

      <div class="resources-intro">
        <p class="eyebrow">Your farm</p>
        <h1 id="resources-title">General farm resources</h1>
        <p>These resources apply across your farm. Choose all that apply, and skip anything you’re not sure about.</p>
      </div>

      <form class="resources-form" @submit.prevent="saveResources">
        <section v-for="(field, index) in fields" :key="`comparison-${index}`" class="resource-section comparison-inputs">
          <h2>Profit comparison for {{ field.name || `Field ${index + 1}` }}</h2>
          <label class="resource-question-label" :for="`current-crop-${index}`">What crop is growing here now?</label>
          <select :id="`current-crop-${index}`" v-model="currentCrops[index]" @change="saved = false">
            <option value="" disabled>Choose a crop</option>
            <option v-for="crop in reportCrops" :key="crop.crop" :value="crop.crop">{{ crop.label }}</option>
          </select>
          <label class="resource-question-label" :for="`water-supply-${index}`">How reliable is the water supply?</label>
          <select :id="`water-supply-${index}`" v-model="waterSupplies[index]" @change="saved = false">
            <option value="full">Reliable / full supply</option>
            <option value="limited">Some limits</option>
            <option value="short">Short or unreliable</option>
          </select>
        </section>
        <section v-for="section in sections" :key="section.title" class="resource-section">
          <h2><span class="section-icon" aria-hidden="true">{{ section.icon }}</span>{{ section.title }}</h2>
          <ResourceQuestion
            v-for="question in section.questions"
            :key="question.id"
            v-model="answers[question.id]"
            v-model:other-detail="otherDetails[question.id]"
            :id="question.id"
            :label="question.label"
            :options="question.options"
            :multiple="question.multiple"
            :exclusive-option="question.exclusiveOption"
          />
        </section>
        <section class="resource-section priority-section">
          <h2>What matters most when choosing crops?</h2>
          <p class="field-card-help">Choose “Equal” if you do not have a strong preference.</p>
          <label v-for="priority in priorityQuestions" :key="priority.key" class="priority-row" :for="`priority-${priority.key}`">
            <span>{{ priority.label }}</span>
            <select :id="`priority-${priority.key}`" v-model.number="priorities[priority.key]" @change="saved = false">
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
        <div class="recommendation-columns">
          <section class="recommendation-panel">
            <h3>Growing fit</h3>
            <p>Metric units · suitability, water, timing, and rotation fit</p>
            <article v-for="candidate in result.insights.candidates.slice(0, 3)" :key="candidate.crop_id" class="recommendation-card">
              <h4>{{ candidate.name }}</h4>
              <p>Fit score: {{ Math.round(candidate.score * 100) }}%</p>
              <p v-if="candidate.water?.crop_need_mm != null">Water needed: {{ Math.round(candidate.water.crop_need_mm) }} mm<span v-if="candidate.water.rainfed_success_prob != null"> · rainfed success: {{ Math.round(candidate.water.rainfed_success_prob * 100) }}%</span></p>
              <p v-if="candidate.plant_window">Planting window: days {{ candidate.plant_window.start_doy }}–{{ candidate.plant_window.end_doy }}</p>
              <p v-for="evidence in candidate.evidence || []" :key="evidence">{{ evidence }}</p>
            </article>
            <p v-for="note in result.insights.notes || []" :key="note" class="field-card-help">{{ note }}</p>
          </section>
          <section class="recommendation-panel">
            <h3>Profit comparison</h3>
            <p>US customary units · estimated dollars per acre</p>
            <p v-if="result.report?.year_odds">
              Year outlook: dry {{ formatPercent(result.report.year_odds.dry) }},
              normal {{ formatPercent(result.report.year_odds.normal) }},
              wet {{ formatPercent(result.report.year_odds.wet) }}
            </p>
            <article v-for="option in result.report?.options.slice(0, 3) || []" :key="option.crop" class="recommendation-card">
              <h4>{{ option.label || cropName(option.crop) }}</h4>
              <p>{{ option.tag.replaceAll('_', ' ') }}</p>
              <p>{{ formatMoney(option.expected_profit_per_acre) }} per acre · {{ formatMoney(option.expected_profit_field) }} for this field</p>
              <p v-if="option.why">{{ option.why }}</p>
            </article>
            <p v-if="!result.report" class="field-card-help">Choose a current crop above to see the profit comparison.</p>
            <p class="field-card-help">Profit inputs are estimates; review the assumptions before using them to plan.</p>
            <details v-if="result.report">
              <summary>Data and assumptions</summary>
              <p v-if="result.report.disclaimer">{{ result.report.disclaimer }}</p>
              <ul>
                <li v-for="note in result.report.data_notes || []" :key="note">{{ note }}</li>
              </ul>
              <p>Data sources: {{ (result.report.data_sources || []).join(', ') }}</p>
            </details>
          </section>
        </div>
      </section>
      </template>
    </section>
  </main>
</template>
