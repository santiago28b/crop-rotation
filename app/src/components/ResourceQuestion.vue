<script setup>
import { computed } from 'vue'

const props = defineProps({
  id: { type: String, required: true },
  label: { type: String, required: true },
  options: { type: Array, required: true },
  multiple: { type: Boolean, default: true },
  modelValue: { type: [Array, String], default: () => [] },
  otherDetail: { type: String, default: '' },
  exclusiveOption: { type: String, default: '' },
})

const emit = defineEmits(['update:modelValue', 'update:otherDetail'])

const selectedValues = computed(() =>
  props.multiple ? props.modelValue : props.modelValue ? [props.modelValue] : [],
)

const hasOther = computed(() => selectedValues.value.includes('Other'))

function isSelected(option) {
  return selectedValues.value.includes(option)
}

function toggle(option) {
  if (!props.multiple) {
    emit('update:modelValue', option)
    return
  }

  let next
  if (isSelected(option)) {
    next = selectedValues.value.filter((value) => value !== option)
  } else if (option === props.exclusiveOption) {
    next = [option]
  } else {
    next = [
      ...selectedValues.value.filter((value) => value !== props.exclusiveOption),
      option,
    ]
  }
  emit('update:modelValue', next)
}
</script>

<template>
  <fieldset class="resource-question">
    <legend>{{ label }}</legend>
    <div class="choice-grid" :class="{ 'choice-grid-single': !multiple }">
      <label
        v-for="option in options"
        :key="option"
        class="choice-card"
        :class="{ 'choice-card-selected': isSelected(option) }"
      >
        <input
          :type="multiple ? 'checkbox' : 'radio'"
          :name="id"
          :value="option"
          :checked="isSelected(option)"
          @change="toggle(option)"
        />
        <span class="choice-indicator" aria-hidden="true"></span>
        <span>{{ option }}</span>
      </label>
    </div>
    <label v-if="hasOther" class="other-detail">
      <span>Please describe</span>
      <input
        :value="otherDetail"
        type="text"
        placeholder="Please describe"
        @input="emit('update:otherDetail', $event.target.value)"
      />
    </label>
  </fieldset>
</template>
