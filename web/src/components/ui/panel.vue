<script setup>
/*
 * Copyright (c) 2026 Cristian D. Moreno — @Kyonax
 * Distributed under the terms of MIT — see LICENSE.
 *
 * The hairline surface every column sits on: a lowercase title bar, an actions
 * slot on the right, and a body that scrolls on its own so the page never does.
 */

defineProps({
  title:  { type: String, default: '' },
  hint:   { type: String, default: '' },
  scroll: { type: Boolean, default: true },
  pad:    { type: Boolean, default: true },
  /* Nested inside another panel: no border, no surface, slim head — the
     parent already drew the box. */
  flat:   { type: Boolean, default: false },
});
</script>

<template>
  <section
    class="ui-panel"
    :class="{ 'is-flat': flat }"
  >
    <header
      v-if="title || $slots.actions"
      class="ui-panel__head"
    >
      <h2 class="ui-panel__title">
        {{ title }}
        <span
          v-if="hint"
          class="ui-panel__hint"
        >{{ hint }}</span>
      </h2>
      <div class="ui-panel__actions">
        <slot name="actions" />
      </div>
    </header>
    <div
      class="ui-panel__body"
      :class="{ 'is-scroll': scroll, 'is-pad': pad }"
    >
      <slot />
    </div>
    <footer
      v-if="$slots.footer"
      class="ui-panel__foot"
    >
      <slot name="footer" />
    </footer>
  </section>
</template>

<style lang="scss" scoped>
.ui-panel {
  @include panel;

  &.is-flat {
    background: transparent;
    border: 0;

    .ui-panel__head {
      background: transparent;
      padding: 0.25rem 0;
      border-bottom: 0;
    }

    .ui-panel__body.is-pad { padding: 0; }
  }

  display: flex;
  flex-direction: column;
  min-height: 0;
  min-width: 0;

  &__head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.5rem;
    padding: 0.45rem 0.6rem;
    border-bottom: 1px solid var(--clr-border-100);
    background: var(--clr-surface-200);
  }

  &__title {
    font-family: "SpaceMono", monospace;
    font-size: var(--fs-tag);
    font-weight: 700;
    letter-spacing: 0.12em;
    text-transform: lowercase;
    color: var(--clr-neutral-100);
    display: flex;
    align-items: baseline;
    gap: 0.5rem;
    min-width: 0;
  }

  &__hint {
    font-weight: 400;
    letter-spacing: 0.02em;
    color: var(--clr-neutral-300);
    text-transform: none;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  &__actions {
    display: flex;
    align-items: center;
    gap: 0.35rem;
    flex: none;
  }

  &__body {
    flex: 1;
    min-height: 0;

    &.is-scroll { overflow: auto; }
    &.is-pad    { padding: 0.6rem; }
  }

  &__foot {
    border-top: 1px solid var(--clr-border-100);
    padding: 0.4rem 0.6rem;
    background: var(--clr-surface-200);
  }
}
</style>
