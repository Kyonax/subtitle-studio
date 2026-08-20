<script setup>
/*
 * Copyright (c) 2026 Cristian D. Moreno — @Kyonax
 * Distributed under the terms of MIT — see LICENSE.
 *
 * track-rail — every subtitle this video carries, and the way to add another.
 *
 * One video, N subtitles: the source transcript plus a track per language.
 * Selecting a chip scopes the text, the style and the preview to that
 * subtitle, so the rest of the panel always speaks about one of them.
 */

import { computed, ref } from 'vue';

import UiButton from '@ui/button.vue';
import UiField from '@ui/field.vue';

import {
  addTrack,
  busy,
  has_transcript,
  setTrack,
  subtitles,
  track,
} from '@composables/use-studio';

const adding = ref(false);
const language = ref('');

/* Common targets, offered as one click each. Any other code still works —
   MADLAD covers 400+ languages and the field takes them all. */
const SUGGESTED = ['en', 'es', 'pt', 'fr', 'de', 'it', 'ja'];

const taken = computed(() => new Set(subtitles.value.map((item) => item.language)));
const offers = computed(() => SUGGESTED.filter((code) => !taken.value.has(code)));
const has_swap = computed(() => taken.value.has('swap'));

const dot = (item) => {
  if (item.styled === 'done') {
    return 'is-done';
  }
  if (item.styled === 'stale' || item.translate === 'stale') {
    return 'is-stale';
  }
  return 'is-pending';
};

const submit = async (code) => {
  const value = String(code || language.value).trim().toLowerCase();
  if (!value) {
    return;
  }
  const started = await addTrack(value);
  if (started) {
    adding.value = false;
    language.value = '';
  }
};
</script>

<template>
  <div class="rail">
    <div class="rail__chips">
      <button
        v-for="item in subtitles"
        :key="item.id || 'source'"
        type="button"
        class="chip"
        :class="{ 'is-active': item.id === track }"
        :data-tip="`${item.name} · ${item.segments} segments · subtitles ${item.styled}`"
        @click="setTrack(item.id)"
      >
        <span
          class="chip__dot"
          :class="dot(item)"
        />
        <span class="chip__name">{{ item.kind === 'source' ? 'source' : item.name }}</span>
        <span class="chip__code">{{ item.language }}</span>
      </button>

      <UiButton
        v-if="has_transcript"
        size="sm"
        variant="ghost"
        :active="adding"
        title="add another language to this video"
        @click="adding = !adding"
      >
        + add
      </UiButton>
    </div>

    <div
      v-if="adding"
      class="rail__add"
    >
      <UiField
        label="new subtitle"
        tip="a language code, for example en, pt, fr or ja. the text is translated offline, then its subtitles are built."
      >
        <input
          v-model="language"
          type="text"
          placeholder="language code"
          :disabled="busy"
          @keydown.enter="submit()"
        >
        <UiButton
          size="sm"
          variant="primary"
          :disabled="busy || !language.trim()"
          @click="submit()"
        >
          add
        </UiButton>
      </UiField>

      <div class="rail__offers">
        <UiButton
          v-for="code in offers"
          :key="code"
          size="sm"
          variant="ghost"
          :disabled="busy"
          @click="submit(code)"
        >
          {{ code }}
        </UiButton>
        <UiButton
          v-if="!has_swap"
          size="sm"
          variant="ghost"
          :disabled="busy"
          title="a two-language video crossed, each part subtitled in the other language"
          @click="submit('swap')"
        >
          swap
        </UiButton>
      </div>
    </div>
  </div>
</template>

<style lang="scss" scoped>
.rail {
  &__chips {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 0.3rem;
  }

  &__add {
    margin-top: 0.4rem;
    padding: 0.4rem;
    border: 1px solid var(--clr-border-100);
    background: var(--clr-surface-200);
  }

  &__offers {
    display: flex;
    flex-wrap: wrap;
    gap: 0.25rem;
    margin-top: 0.3rem;
  }
}

.chip {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  padding: 0.25rem 0.45rem;
  background: transparent;
  border: 1px solid var(--clr-border-100);
  color: var(--clr-neutral-200);
  font-size: var(--fs-meta);
  letter-spacing: 0.04em;
  cursor: pointer;

  &:hover {
    border-color: var(--clr-primary-100);
    color: var(--clr-primary-100);
  }

  &.is-active {
    border-color: var(--clr-primary-100);
    color: var(--clr-primary-100);
    background: color-mix(in srgb, var(--clr-primary-100) 12%, transparent);
  }

  &__dot {
    width: 0.4rem;
    height: 0.4rem;
    flex: none;
    background: var(--clr-neutral-400);

    &.is-done { background: var(--clr-success-100); }
    &.is-stale { background: var(--clr-warning-100); }
  }

  &__code {
    color: var(--clr-neutral-300);
    text-transform: uppercase;
  }
}
</style>
