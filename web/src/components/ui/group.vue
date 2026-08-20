<script setup>
/*
 * Copyright (c) 2026 Cristian D. Moreno — @Kyonax
 * Distributed under the terms of MIT — see LICENSE.
 *
 * A titled band of controls: the mono uppercase section label from the
 * nano-core dashboard, then an auto-fitting grid of fields. Controls that need
 * the full width mark themselves with `span`.
 */

defineProps({
  label: { type: String, default: '' },
  note:  { type: String, default: '' },
  columns: { type: String, default: '10rem' },
});
</script>

<template>
  <section class="group">
    <header
      v-if="label || $slots.actions"
      class="group__head"
    >
      <h3
        v-if="label"
        class="group__label"
      >
        {{ label }}
      </h3>
      <div class="group__actions">
        <slot name="actions" />
      </div>
    </header>
    <div
      class="group__grid"
      :style="{ '--group-columns': columns }"
    >
      <slot />
    </div>
    <p
      v-if="note"
      class="group__note"
    >
      {{ note }}
    </p>
  </section>
</template>

<style lang="scss" scoped>
.group {
  & + & { margin-top: 0.9rem; }

  &__head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.5rem;
    padding-bottom: 0.3rem;
    margin-bottom: 0.3rem;
    border-bottom: 1px solid var(--clr-border-100);
  }

  &__label {
    font-size: var(--fs-tag);
    font-weight: 400;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--clr-neutral-300);
  }

  &__actions {
    display: flex;
    align-items: center;
    gap: 0.25rem;
  }

  &__grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(var(--group-columns), 1fr));
    gap: 0 0.9rem;
    align-items: start;
  }

  &__note {
    margin: 0.4rem 0 0;
    font-size: var(--fs-meta);
    line-height: 1.4;
    color: var(--clr-neutral-300);
  }
}
</style>
