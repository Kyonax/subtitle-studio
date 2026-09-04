<script setup>
/*
 * Copyright (c) 2026 Cristian D. Moreno — @Kyonax
 * Distributed under the terms of MIT — see LICENSE.
 *
 * combobox — a select you can type into, for lists too long to scroll.
 *
 * A plain <select> stops working somewhere past a few dozen entries, and the
 * font list on a normal machine is in the hundreds. So: the closed state reads
 * as one value like any other control, focus turns it into a search box, and
 * what you type filters. Prefix matches rank above contains matches, because
 * typing "rob" means Roboto and not "Kanit Bold Rob".
 *
 * Two rules the page depends on:
 *   Only a real option can be committed. Free text reverts on blur — an
 *   invalid value here is a hard error three stages later, and the guard is
 *   worth more than the freedom to type anything.
 *   The rendered list is capped and SAYS it is capped. A silent truncation
 *   reads as "that's all there is" when it is not.
 */

import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue';

const props = defineProps({
  modelValue:  { type: String, default: '' },
  /* [{ value, label?, tag? }] or plain strings */
  options:     { type: Array, default: () => [] },
  placeholder: { type: String, default: 'search' },
  limit:       { type: Number, default: 200 },
  disabled:    { type: Boolean, default: false },
});

const emit = defineEmits(['update:modelValue']);

const root = ref(null);
const input = ref(null);
const list = ref(null);
const open = ref(false);
const query = ref('');
const active = ref(0);

const items = computed(() => props.options.map((o) => (
  typeof o === 'string' ? { value: o, label: o, tag: '' } : { label: o.value, tag: '', ...o }
)));

const current = computed(() => items.value.find((i) => i.value === props.modelValue) || null);

/* Prefix hits first, then contains hits, each in the catalogue's own order. */
const matches = computed(() => {
  const q = query.value.trim().toLowerCase();
  if (!q) {
    return items.value;
  }
  const prefix = [];
  const contains = [];
  for (const item of items.value) {
    const hay = `${item.label} ${item.tag}`.toLowerCase();
    const at = hay.indexOf(q);
    if (at === 0) {
      prefix.push(item);
    } else if (at > 0) {
      contains.push(item);
    }
  }
  return prefix.concat(contains);
});

const shown = computed(() => matches.value.slice(0, props.limit));
const hidden = computed(() => Math.max(0, matches.value.length - shown.value.length));

watch(matches, () => { active.value = 0; });

const scrollActiveIntoView = async () => {
  await nextTick();
  list.value?.querySelector('.combo__option.is-active')?.scrollIntoView({ block: 'nearest' });
};

const show = () => {
  if (props.disabled) {
    return;
  }
  open.value = true;
  query.value = '';
  active.value = Math.max(0, shown.value.findIndex((i) => i.value === props.modelValue));
  scrollActiveIntoView();
};

const hide = () => {
  open.value = false;
  query.value = '';
};

const commit = (item) => {
  if (item && item.value !== props.modelValue) {
    emit('update:modelValue', item.value);
  }
  hide();
  input.value?.blur();
};

const move = (step) => {
  if (!open.value) {
    show();
    return;
  }
  const count = shown.value.length;
  if (count) {
    active.value = (active.value + step + count) % count;
    scrollActiveIntoView();
  }
};

/* Enter takes the highlighted row, or an exact typed name if there is one. */
const onEnter = () => {
  if (!open.value) {
    return;
  }
  const typed = query.value.trim().toLowerCase();
  const exact = items.value.find((i) => i.label.toLowerCase() === typed);
  commit(exact || shown.value[active.value] || null);
};

const onBlur = () => {
  /* Let a click on an option land before the list disappears. */
  window.setTimeout(() => { if (open.value) { hide(); } }, 120);
};

const onDocumentDown = (event) => {
  if (open.value && root.value && !root.value.contains(event.target)) {
    hide();
  }
};

onMounted(() => document.addEventListener('mousedown', onDocumentDown));
onBeforeUnmount(() => document.removeEventListener('mousedown', onDocumentDown));
</script>

<template>
  <div
    ref="root"
    class="combo"
    :class="{ 'is-open': open, 'is-disabled': disabled }"
  >
    <input
      ref="input"
      class="combo__input"
      type="text"
      autocomplete="off"
      spellcheck="false"
      :disabled="disabled"
      :value="open ? query : (current?.label || modelValue)"
      :placeholder="open ? placeholder : ''"
      @focus="show"
      @blur="onBlur"
      @input="query = $event.target.value; open = true"
      @keydown.down.prevent="move(1)"
      @keydown.up.prevent="move(-1)"
      @keydown.enter.prevent="onEnter"
      @keydown.esc.prevent="hide"
      @keydown.tab="hide"
    >
    <span
      class="combo__caret"
      aria-hidden="true"
    >{{ open ? '×' : '▾' }}</span>

    <div
      v-if="open"
      ref="list"
      class="combo__list"
    >
      <button
        v-for="(item, index) in shown"
        :key="item.value"
        type="button"
        class="combo__option"
        :class="{
          'is-active': index === active,
          'is-current': item.value === modelValue,
        }"
        @mousedown.prevent="commit(item)"
        @mouseenter="active = index"
      >
        <span class="combo__name">{{ item.label }}</span>
        <span
          v-if="item.tag"
          class="combo__tag"
        >{{ item.tag }}</span>
      </button>

      <p
        v-if="!shown.length"
        class="combo__note"
      >
        nothing matches "{{ query }}"
      </p>
      <p
        v-else-if="hidden"
        class="combo__note"
      >
        {{ hidden }} more not shown — keep typing to narrow
      </p>
    </div>
  </div>
</template>

<style lang="scss" scoped>
.combo {
  position: relative;
  width: 100%;
  min-width: 0;

  &.is-disabled { opacity: 0.6; }

  &__input {
    width: 100%;
    min-width: 0;
    background: var(--clr-neutral-500);
    border: 1px solid var(--clr-border-100);
    color: var(--clr-neutral-100);
    padding: 0.3rem 1.4rem 0.3rem 0.4rem;
    font-size: var(--fs-200);

    &:focus-visible {
      border-color: var(--clr-primary-100);
      outline: none;
    }
  }

  &__caret {
    position: absolute;
    top: 50%;
    right: 0.45rem;
    transform: translateY(-50%);
    font-size: var(--fs-meta);
    color: var(--clr-neutral-300);
    pointer-events: none;
  }

  &__list {
    position: absolute;
    z-index: 20;
    top: calc(100% + 2px);
    left: 0;
    right: 0;
    max-height: 15rem;
    overflow-y: auto;
    background: var(--clr-neutral-500);
    border: 1px solid var(--clr-primary-100);
  }

  &__option {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 0.5rem;
    width: 100%;
    text-align: left;
    background: none;
    border: none;
    color: var(--clr-neutral-100);
    padding: 0.3rem 0.45rem;
    font-size: var(--fs-200);
    font-family: inherit;
    cursor: pointer;

    &.is-active {
      background: var(--clr-primary-100);
      color: var(--clr-neutral-500);

      .combo__tag { color: var(--clr-neutral-500); }
    }

    &.is-current .combo__name { font-weight: 700; }
  }

  &__name {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  &__tag {
    flex: none;
    font-size: var(--fs-meta);
    color: var(--clr-neutral-300);
    letter-spacing: 0.04em;
  }

  &__note {
    margin: 0;
    padding: 0.35rem 0.45rem;
    font-size: var(--fs-meta);
    line-height: 1.4;
    color: var(--clr-neutral-300);
    border-top: 1px solid var(--clr-border-100);
  }
}
</style>
