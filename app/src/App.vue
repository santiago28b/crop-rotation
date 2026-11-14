<script setup>
import { onMounted, ref } from 'vue'
import { requestLocation } from './geolocation.js'
import FieldPicker from './components/FieldPicker.vue'
import FieldInfoPage from './components/FieldInfoPage.vue'
import ResourcesPage from './components/ResourcesPage.vue'
import WelcomeScreen from './components/WelcomeScreen.vue'

const currentPage = ref('welcome')
const fieldStarted = ref(false)
const fieldInfoStarted = ref(false)
const resourcesStarted = ref(false)
const fieldBoundaries = ref([])
const confirmedFieldData = ref({ profiles: [], answers: [] })

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
  />
</template>
