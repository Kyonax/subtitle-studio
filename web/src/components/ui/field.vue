<script setup>
/*
 * Copyright (c) 2026 Cristian D. Moreno — @Kyonax
 * Distributed under the terms of MIT — see LICENSE.
 *
 * One control, one shape (the nano-core widget): a head row carrying the label
 * and a `?` mark, the control underneath. Every control on the page is built
 * from this, which is what makes a wall of settings scannable — the eye learns
 * one rhythm instead of five.
 */

import UiHelpMark from '@ui/help-mark.vue';

defineProps({
  label: { type: String, default: '' },
  tip:   { type: String, default: '' },
  span:  { type: Boolean, default: false },
  row:   { type: Boolean, default: false },
});
</script>

<template>
  <div
    class="widget"
    :class="{ 'is-span': span, 'is-row': row }"
  >
    <div
      v-if="label"
      class="widget__head"
    >
      <label class="widget__label">{{ label }}</label>
      <UiHelpMark
        v-if="tip"
        :tip="tip"
      />
    </div>
    <div class="widget__control">
      <slot />
    </div>
  </div>
</template>

<style lang="scss" scoped>
.widget {
  padding: 0.35rem 0;
  min-width: 0;

  &.is-span { grid-column: 1 / -1; }

  &.is-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.5rem;

    .widget__head { margin-bottom: 0; }
  }

  &__head {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    margin-bottom: 0.25rem;
    min-width: 0;
  }

  &__label {
    font-size: var(--fs-meta);
    letter-spacing: 0.04em;
    color: var(--clr-neutral-200);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  &__control {
    display: flex;
    align-items: center;
    gap: 0.35rem;
    min-width: 0;

    :deep(input[type="text"]),
    :deep(input[type="search"]),
    :deep(input[type="number"]),
    :deep(select),
    :deep(textarea) {
      width: 100%;
      min-width: 0;
      background: var(--clr-neutral-500);
      border: 1px solid var(--clr-border-100);
      color: var(--clr-neutral-100);
      padding: 0.3rem 0.4rem;
      font-size: var(--fs-200);

      &:focus-visible {
        border-color: var(--clr-primary-100);
        outline: none;
      }

      &:disabled {
        color: var(--clr-neutral-400);
        cursor: not-allowed;
      }
    }

    :deep(input[type="color"]) {
      width: 2.2rem;
      height: 1.7rem;
      padding: 0;
      background: transparent;
      border: 1px solid var(--clr-border-100);
      cursor: pointer;
      flex: none;
    }
  }
}
</style>
