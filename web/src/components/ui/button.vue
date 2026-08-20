<script setup>
/*
 * Copyright (c) 2026 Cristian D. Moreno — @Kyonax
 * Distributed under the terms of MIT — see LICENSE.
 */

import { computed, useAttrs } from 'vue';

defineOptions({ inheritAttrs: false });

const props = defineProps({
  variant:  {
    type: String,
    default: 'secondary',
    validator: (v) => ['primary', 'secondary', 'ghost', 'danger'].includes(v),
  },
  size:     {
    type: String,
    default: 'md',
    validator: (s) => ['sm', 'md', 'lg'].includes(s),
  },
  type:     { type: String, default: 'button' },
  disabled: { type: Boolean, default: false },
  active:   { type: Boolean, default: false },
  block:    { type: Boolean, default: false },
});

defineEmits(['click']);

const attrs = useAttrs();

const class_list = computed(() => [
  'ui-button',
  `ui-button--${props.variant}`,
  `ui-button--size-${props.size}`,
  props.active ? 'is-active' : null,
  props.block ? 'ui-button--block' : null,
]);
</script>

<template>
  <button
    :type="type"
    :disabled="disabled"
    :class="class_list"
    v-bind="attrs"
    @click="$emit('click', $event)"
  >
    <slot />
  </button>
</template>

<style lang="scss" scoped>
.ui-button {
  cursor: pointer;
  font-family: "SpaceMono", monospace;
  letter-spacing: 0.04em;
  background: transparent;
  border: 1px solid var(--clr-border-100);
  color: var(--clr-neutral-200);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.4rem;
  line-height: 1;
  white-space: nowrap;
  transition:
    background-color 0.15s var(--ease-standard),
    border-color 0.15s var(--ease-standard),
    color 0.15s var(--ease-standard);

  &:disabled {
    cursor: not-allowed;
    opacity: 0.4;
  }

  &--block {
    width: 100%;
  }

  &--size-sm { padding: 0.3rem 0.5rem; font-size: var(--fs-meta); }
  &--size-md { padding: 0.5rem 0.8rem; font-size: var(--fs-200); }
  &--size-lg { padding: 0.7rem 1.1rem; font-size: var(--fs-300); }

  &--primary {
    background: var(--clr-primary-100);
    border-color: var(--clr-primary-100);
    color: var(--clr-neutral-500);
    font-weight: 700;

    &:hover:not(:disabled),
    &:focus-visible {
      background: var(--clr-primary-50);
      border-color: var(--clr-primary-50);
    }
  }

  &--secondary:hover:not(:disabled),
  &--secondary:focus-visible {
    color: var(--clr-primary-100);
    border-color: var(--clr-primary-100);
  }

  &--ghost {
    border-color: transparent;
    color: var(--clr-neutral-300);

    &:hover:not(:disabled),
    &:focus-visible {
      color: var(--clr-primary-100);
      border-color: var(--clr-border-100);
    }
  }

  &--danger {
    color: var(--clr-error-100);
    border-color: color-mix(in srgb, var(--clr-error-100) 40%, transparent);

    &:hover:not(:disabled),
    &:focus-visible {
      background: color-mix(in srgb, var(--clr-error-100) 12%, transparent);
      border-color: var(--clr-error-100);
    }
  }

  &.is-active {
    color: var(--clr-primary-100);
    border-color: var(--clr-primary-100);
    background: color-mix(in srgb, var(--clr-primary-100) 10%, transparent);
  }
}
</style>
