<script setup>
/*
 * Copyright (c) 2026 Cristian D. Moreno — @Kyonax
 * Distributed under the terms of MIT — see LICENSE.
 *
 * The activity row: what is running, how far it got, and its latest message.
 * An unknown fraction pulses instead of lying about progress.
 */

import { computed } from 'vue';

const props = defineProps({
  label:    { type: String, default: '' },
  detail:   { type: String, default: '' },
  fraction: { type: Number, default: 0 },
  indeterminate: { type: Boolean, default: false },
});

const percent = computed(() => Math.round(Math.min(Math.max(props.fraction || 0, 0), 1) * 100));
</script>

<template>
  <div class="ui-progress">
    <div class="ui-progress__head">
      <span class="ui-progress__label">{{ label }}</span>
      <span
        v-if="!indeterminate"
        class="ui-progress__percent"
      >{{ percent }}%</span>
    </div>
    <div class="ui-progress__track">
      <div
        class="ui-progress__fill"
        :class="{ 'is-indeterminate': indeterminate }"
        :style="indeterminate ? null : { width: `${percent}%` }"
      />
    </div>
    <p
      v-if="detail"
      class="ui-progress__detail"
    >
      {{ detail }}
    </p>
  </div>
</template>

<style lang="scss" scoped>
.ui-progress {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;

  &__head {
    display: flex;
    justify-content: space-between;
    gap: 0.5rem;
    font-size: var(--fs-meta);
    color: var(--clr-primary-100);
    letter-spacing: 0.06em;
  }

  &__track {
    height: 3px;
    background: var(--clr-surface-300);
    overflow: hidden;
  }

  &__fill {
    height: 100%;
    background: var(--clr-primary-100);
    transition: width 0.2s var(--ease-standard);

    &.is-indeterminate {
      width: 35%;
      background: repeating-linear-gradient(
        90deg,
        var(--clr-primary-100) 0 0.5rem,
        transparent 0.5rem 1rem
      );
      animation: kyo-stripe 0.7s linear infinite;
    }
  }

  &__detail {
    margin: 0;
    font-size: var(--fs-meta);
    color: var(--clr-neutral-300);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
}
</style>
