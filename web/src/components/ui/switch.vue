<script setup>
/*
 * Copyright (c) 2026 Cristian D. Moreno — @Kyonax
 * Distributed under the terms of MIT — see LICENSE.
 *
 * The squared slider from the nano-core dashboard: no radius, hairline border,
 * a knob that travels. role="switch" and a real button, so the keyboard works.
 */

defineProps({
  modelValue: { type: Boolean, default: false },
  disabled: { type: Boolean, default: false },
  label: { type: String, default: 'toggle' },
});

const emit = defineEmits(['update:modelValue']);
</script>

<template>
  <button
    type="button"
    class="ui-switch"
    :class="{ 'is-on': modelValue }"
    role="switch"
    :aria-checked="modelValue"
    :aria-label="label"
    :disabled="disabled"
    @click="emit('update:modelValue', !modelValue)"
  >
    <span class="ui-switch__knob" />
  </button>
</template>

<style lang="scss" scoped>
.ui-switch {
  width: 2.6rem;
  min-width: 2.6rem;
  height: 1.3rem;
  padding: 0.15rem;
  border: 1px solid var(--clr-border-100);
  background: var(--clr-surface-100);
  display: inline-flex;
  align-items: center;
  cursor: pointer;
  /* never let a flex parent squeeze the track, the knob would escape it */
  flex-shrink: 0;

  &:disabled {
    cursor: not-allowed;
    opacity: 0.4;
  }

  &__knob {
    width: 0.9rem;
    height: 0.9rem;
    background: var(--clr-neutral-400);
    transform: translateX(0);
    transition: transform 0.15s var(--ease-standard), background 0.15s var(--ease-standard);
  }

  &.is-on {
    border-color: var(--clr-primary-100);

    .ui-switch__knob {
      background: var(--clr-primary-100);
      transform: translateX(1.2rem);
    }
  }
}
</style>
