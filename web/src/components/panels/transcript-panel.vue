<script setup>
/*
 * Copyright (c) 2026 Cristian D. Moreno — @Kyonax
 * Distributed under the terms of MIT — see LICENSE.
 *
 * transcript-panel — the timed text, editable in place.
 *
 * An edit here goes through the server, which retimes the segment's words
 * (Law 1 of the edit-integrity contract) so the words that build the on-screen
 * chunks can never drift from the text you typed. Selecting a row moves the
 * preview to that row. j/k walk the list, like the TUI.
 */

import { computed, nextTick, ref } from 'vue';

import UiBadge from '@ui/badge.vue';
import UiButton from '@ui/button.vue';
import UiPanel from '@ui/panel.vue';

import {
  busy,
  has_transcript,
  runStage,
  saveSegment,
  segments,
  selectSegment,
  selected_segment,
  state,
  track,
} from '@composables/use-studio';

const filter = ref('');
const editing_id = ref(null);
const draft = ref('');
const editor = ref(null);
const list = ref(null);

const translated = computed(() => Boolean(state.value?.transcript?.translated_from));

const rows = computed(() => {
  const needle = filter.value.trim().toLowerCase();
  if (!needle) {
    return segments.value;
  }
  return segments.value.filter((segment) => segment.text.toLowerCase().includes(needle));
});

const clock = (seconds) => {
  const whole = Math.floor(seconds);
  const minutes = String(Math.floor(whole / 60)).padStart(2, '0');
  const rest = String(whole % 60).padStart(2, '0');
  return `${minutes}:${rest}.${String(Math.round((seconds - whole) * 100)).padStart(2, '0')}`;
};

const startEdit = async (segment) => {
  editing_id.value = segment.id;
  draft.value = segment.text;
  selectSegment(segment.id);
  await nextTick();
  editor.value?.[0]?.focus();
  editor.value?.[0]?.select();
};

const cancelEdit = () => {
  editing_id.value = null;
  draft.value = '';
};

const commitEdit = async (segment) => {
  const text = draft.value.trim();
  if (!text || text === segment.text) {
    cancelEdit();
    return;
  }
  const saved = await saveSegment(segment.id, text);
  if (saved) {
    cancelEdit();
  }
};

const move = (direction) => {
  const items = rows.value;
  if (!items.length) {
    return;
  }
  const index = items.findIndex((segment) => segment.id === selected_segment.value);
  const next = Math.min(Math.max((index === -1 ? 0 : index) + direction, 0), items.length - 1);
  selectSegment(items[next].id);
  list.value?.querySelector('.row.is-selected')?.scrollIntoView({ block: 'nearest' });
};

const onKey = (event) => {
  if (editing_id.value !== null) {
    return;
  }
  const key = event.key;
  if (key === 'j' || key === 'ArrowDown') {
    event.preventDefault();
    move(1);
  } else if (key === 'k' || key === 'ArrowUp') {
    event.preventDefault();
    move(-1);
  } else if (key === 'Enter') {
    const segment = rows.value.find((item) => item.id === selected_segment.value);
    if (segment) {
      event.preventDefault();
      startEdit(segment);
    }
  } else if (key === 't' && selected_segment.value !== null && !busy.value) {
    event.preventDefault();
    runStage('relisten', { segment: selected_segment.value });
  }
};
</script>

<template>
  <UiPanel
    flat
    title=""
    :hint="translated ? `translated from ${state?.transcript?.translated_from}` : 'source text, edits retime the words'"
    :pad="false"
  >
    <template #actions>
      <input
        v-model="filter"
        class="search"
        type="search"
        placeholder="filter"
      >
      <UiButton
        size="sm"
        variant="ghost"
        :disabled="busy || selected_segment === null || translated"
        data-tip="transcribe this one segment again from its audio (t)"
        @click="runStage('relisten', { segment: selected_segment })"
      >
        relisten row
      </UiButton>
      <UiButton
        size="sm"
        variant="ghost"
        :disabled="busy || !has_transcript"
        data-tip="transcribe the whole file again, the current text is kept as .bak"
        @click="runStage('transcribe')"
      >
        relisten all
      </UiButton>
      <UiButton
        size="sm"
        variant="ghost"
        :disabled="busy || !has_transcript"
        data-tip="detect the language of every segment again"
        @click="runStage('languages')"
      >
        languages
      </UiButton>
    </template>

    <div
      ref="list"
      class="rows"
      tabindex="0"
      @keydown="onKey"
    >
      <p
        v-if="!has_transcript"
        class="empty"
      >
        nothing transcribed yet — run stage 1 and the timed text lands here
      </p>

      <div
        v-for="segment in rows"
        :key="segment.id"
        class="row"
        :class="{
          'is-selected': segment.id === selected_segment,
          'is-editing': segment.id === editing_id,
        }"
        @click="selectSegment(segment.id)"
        @dblclick="startEdit(segment)"
      >
        <div class="row__meta">
          <span class="row__time">{{ clock(segment.start) }}</span>
          <UiBadge
            v-if="segment.language"
            state="neutral"
            :label="segment.language"
          />
          <span
            v-if="segment.speaker_name"
            class="row__speaker"
          >{{ segment.speaker_name }}</span>
          <span class="row__spacer" />
          <div class="row__tools">
            <UiButton
              size="sm"
              variant="ghost"
              data-tip="edit this text (enter)"
              @click.stop="startEdit(segment)"
            >
              edit
            </UiButton>
            <UiButton
              size="sm"
              variant="ghost"
              :disabled="busy || translated"
              data-tip="transcribe this one segment again (t)"
              @click.stop="runStage('relisten', { segment: segment.id })"
            >
              relisten
            </UiButton>
          </div>
        </div>

        <div class="row__body">
          <textarea
            v-if="segment.id === editing_id"
            ref="editor"
            v-model="draft"
            class="row__editor"
            rows="2"
            @keydown.enter.exact.prevent="commitEdit(segment)"
            @keydown.esc.prevent="cancelEdit"
            @blur="commitEdit(segment)"
          />
          <p
            v-else
            class="row__text"
            :class="{ 'is-low': segment.low_confidence }"
            :title="segment.source_text ? `source: ${segment.source_text}` : ''"
          >
            {{ segment.text }}
          </p>
        </div>
      </div>
    </div>
  </UiPanel>
</template>

<style lang="scss" scoped>
.search {
  width: 7rem;
  background: var(--clr-neutral-500);
  border: 1px solid var(--clr-border-100);
  color: var(--clr-neutral-100);
  padding: 0.2rem 0.35rem;
  font-size: var(--fs-meta);

  &:focus-visible {
    border-color: var(--clr-primary-100);
    outline: none;
  }
}

.rows {
  height: 100%;
  overflow: auto;
  outline: none;
}

.empty {
  margin: 0;
  padding: 1rem 0.8rem;
  color: var(--clr-neutral-300);
  font-size: var(--fs-200);
}

.row {
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
  padding: 0.35rem 0.6rem;
  border-bottom: 1px solid color-mix(in srgb, var(--clr-border-100) 45%, transparent);
  cursor: pointer;

  &:hover { background: var(--clr-surface-200); }

  &.is-selected {
    background: color-mix(in srgb, var(--clr-primary-100) 12%, transparent);
    box-shadow: inset 2px 0 0 var(--clr-primary-100);
  }

  &__time {
    font-size: var(--fs-meta);
    color: var(--clr-neutral-300);
  }

  &__meta {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    min-height: 1.4rem;
  }

  &__spacer { flex: 1; }

  &__speaker {
    font-size: var(--fs-meta);
    color: var(--clr-secondary-50);
  }

  &__body { min-width: 0; }

  &__text {
    margin: 0;
    font-size: var(--fs-200);
    color: var(--clr-neutral-100);
    line-height: 1.45;
    overflow-wrap: anywhere;

    &.is-low { color: var(--clr-warning-100); }
  }

  &__editor {
    width: 100%;
    resize: vertical;
    background: var(--clr-neutral-500);
    border: 1px solid var(--clr-primary-100);
    color: var(--clr-neutral-100);
    padding: 0.25rem 0.35rem;
    font-size: var(--fs-200);
    font-family: inherit;
    line-height: 1.45;

    &:focus-visible { outline: none; }
  }

  &__tools {
    display: flex;
    gap: 0.2rem;
    opacity: 0;
    transition: opacity 0.15s var(--ease-standard);
  }

  &:hover .row__tools,
  &.is-selected .row__tools { opacity: 1; }
}
</style>
