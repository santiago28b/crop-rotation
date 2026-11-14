<script setup>
import { nextTick, onMounted, ref } from 'vue'
import { requestLocation } from './geolocation.js'
import FieldPicker from './components/FieldPicker.vue'
import FieldInfoPage from './components/FieldInfoPage.vue'
import ResourcesPage from './components/ResourcesPage.vue'
import RecommendationsPage from './components/RecommendationsPage.vue'
import WelcomeScreen from './components/WelcomeScreen.vue'

const currentPage = ref('welcome')
const fieldStarted = ref(false)
const fieldInfoStarted = ref(false)
const resourcesStarted = ref(false)
const fieldBoundaries = ref([])
const confirmedFieldData = ref({ profiles: [], answers: [] })
const recommendationFields = ref([])
const recommendationResults = ref([])
const recommendationsLoading = ref(false)
const recommendationsError = ref('')

onMounted(() => {
  requestLocation().catch(() => {})
})

function openFieldPicker() {
  fieldStarted.value = true
  currentPage.value = 'field'
}

function openFieldInfo(fields) {
  fieldBoundaries.value = fields
  fieldInfoStarted.value = true
  currentPage.value = 'field-info'
}

function openResources(data) {
  confirmedFieldData.value = data
  resourcesStarted.value = true
  currentPage.value = 'resources'
}

function openRecommendations({ fields }) {
  recommendationFields.value = [...fields]
  recommendationResults.value = []
  recommendationsError.value = ''
  recommendationsLoading.value = true
  currentPage.value = 'recommendations'
}

function showRecommendations({ results }) {
  recommendationResults.value = results
  recommendationsLoading.value = false
}

function showRecommendationsError(message) {
  recommendationsError.value = message
  recommendationsLoading.value = false
}

async function editAnswers() {
  currentPage.value = 'resources'
  await nextTick()
  window.scrollTo({ top: 0 })
}
</script>

<template>
  <WelcomeScreen v-if="currentPage === 'welcome'" @pick-field="openFieldPicker" />
  <FieldPicker
    v-if="fieldStarted"
    v-show="currentPage === 'field'"
    :active="currentPage === 'field'"
    @go-back="currentPage = 'welcome'"
    @continue="openFieldInfo"
  />
  <FieldInfoPage
    v-if="fieldInfoStarted"
    v-show="currentPage === 'field-info'"
    :fields="fieldBoundaries"
    @go-back="currentPage = 'field'"
    @continue="openResources"
  />
  <ResourcesPage
    v-if="resourcesStarted"
    v-show="currentPage === 'resources'"
    :fields="fieldBoundaries"
    :profiles="confirmedFieldData.profiles"
    :field-answers="confirmedFieldData.answers"
    @go-back="currentPage = 'field-info'"
    @recommendations-started="openRecommendations"
    @recommendations-ready="showRecommendations"
    @recommendations-error="showRecommendationsError"
  />
  <RecommendationsPage
    v-if="currentPage === 'recommendations'"
    :fields="recommendationFields"
    :results="recommendationResults"
    :loading="recommendationsLoading"
    :error="recommendationsError"
    @go-back="editAnswers"
  />
</template>
