<script setup>
import { reactive, ref, watch } from 'vue'
import ResourceQuestion from './ResourceQuestion.vue'

const emit = defineEmits(['go-back'])
const saved = ref(false)

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

function saveResources() {
  saved.value = true
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

        <div class="resource-submit-row">
          <p v-if="saved" class="resource-saved" role="status">Your answers are saved for this demo.</p>
          <button class="primary-button" type="submit">
            {{ saved ? 'Saved' : 'Save resources' }}
            <span aria-hidden="true">✓</span>
          </button>
        </div>
      </form>
    </section>
  </main>
</template>
