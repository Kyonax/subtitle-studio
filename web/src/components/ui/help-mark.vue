<script setup>
/*
 * Copyright (c) 2026 Cristian D. Moreno — @Kyonax
 * Distributed under the terms of MIT — see LICENSE.
 *
 * The `?` mark: a bordered square carrying a tooltip, keyboard focusable.
 * Explanations live in here rather than under every field — the same move the
 * nano-core dashboard makes, and the reason a dense panel stays readable.
 */

defineProps({
  tip: { type: String, required: true },
});
</script>

<template>
  <span
    class="help-mark"
    :data-tip="tip"
    tabindex="0"
  >?</span>
</template>

<style lang="scss" scoped>
.help-mark {
  width: 1.05rem;
  height: 1.05rem;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: var(--fs-meta);
  color: var(--clr-neutral-300);
  border: 1px solid var(--clr-border-100);
  cursor: help;
  flex-shrink: 0;

  &:hover,
  &:focus-visible {
    color: var(--clr-primary-100);
    border-color: var(--clr-primary-100);
  }
}
</style>
