<script setup>
/*
 * Copyright (c) 2026 Cristian D. Moreno — @Kyonax
 * Distributed under the terms of MIT — see LICENSE.
 *
 * The one word that says where something stands.
 *
 * The server speaks in file terms — done, fresh, stale, pending, missing — five
 * words for four situations, which is five things to learn. Here they become
 * ONE vocabulary, said the same way everywhere on the page: ready · out of
 * date · not made yet · working. A caller may still pass a `label` for a
 * detail worth showing instead ("6 segments").
 */

import { computed } from 'vue';

const props = defineProps({
  state: { type: String, default: 'pending' },
  label: { type: String, default: '' },
});

const WORDS = {
  done: 'ready',
  fresh: 'ready',
  ok: 'ready',
  stale: 'out of date',
  pending: 'not made yet',
  missing: 'not made yet',
  working: 'working',
  error: 'failed',
  'n/a': 'spoken',
  neutral: '',
};

const TONES = {
  done: 'ok',
  fresh: 'ok',
  ok: 'ok',
  stale: 'warn',
  pending: 'off',
  missing: 'off',
  working: 'run',
  error: 'error',
  'n/a': 'off',
  neutral: 'off',
};

const text = computed(() => props.label || WORDS[props.state] || props.state);
const tone = computed(() => TONES[props.state] || 'off');
</script>

<template>
  <span
    class="ui-badge kyo-chip"
    :class="`ui-badge--${tone}`"
  >
    <i
      v-if="!label"
      class="ui-badge__dot"
    />{{ text }}</span>
</template>

<style lang="scss" scoped>
.ui-badge {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  padding: 0.15rem 0.4rem;
  font-size: var(--fs-tag);
  text-transform: lowercase;
  color: var(--clr-neutral-300);
  white-space: nowrap;

  &__dot {
    width: 0.4rem;
    height: 0.4rem;
    background: currentColor;
    flex: none;
  }

  &--ok    { color: var(--clr-success-100); }
  &--warn  { color: var(--clr-warning-100); }
  &--run   { color: var(--clr-primary-100); }
  &--error { color: var(--clr-error-100); }
  &--off   { color: var(--clr-neutral-300); }
}
</style>
