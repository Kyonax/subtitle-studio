<script setup>
/*
 * Copyright (c) 2026 Cristian D. Moreno — @Kyonax
 * Distributed under the terms of MIT — see LICENSE.
 *
 * subtitles-panel — one video, N subtitles, iterated one at a time.
 *
 * The rail picks which subtitle everything below is about: its text, its look,
 * the preview in the middle column. The box under the rail is that subtitle's
 * own state and its own actions (build, burn, download, remove), the way an
 * array item carries its controls in the nano-core dashboard. Delivery sits in
 * the footer because it is the last thing you do and it concerns all of them.
 */

import { computed, ref, watch } from 'vue';

import api from '@api/client';
import UiBadge from '@ui/badge.vue';
import UiButton from '@ui/button.vue';
import UiPanel from '@ui/panel.vue';

import StylesPanel from '@panels/styles-panel.vue';
import TrackRail from '@panels/track-rail.vue';
import TranscriptPanel from '@panels/transcript-panel.vue';

import {
  buildTrack,
  buildTracks,
  burnTrack,
  busy,
  current_track,
  has_transcript,
  removeTrack,
  subtitles,
} from '@composables/use-studio';

const TABS = [
  { id: 'text', label: 'text' },
  { id: 'style', label: 'style' },
];

const tab = ref('text');
const confirming = ref('');

watch(current_track, () => {
  confirming.value = '';
});

const all_ids = computed(() => subtitles.value.map((item) => item.id));

const text_state = computed(() => {
  const item = current_track.value;
  if (!item) {
    return 'pending';
  }
  return item.kind === 'source' ? 'done' : item.translate;
});

const remove = async (id) => {
  if (confirming.value !== id) {
    confirming.value = id;
    return;
  }
  confirming.value = '';
  await removeTrack(id);
};
</script>

<template>
  <UiPanel
    title="subtitles"
    :hint="`${subtitles.length} track(s) on this video`"
    :scroll="false"
  >
    <template #actions>
      <UiButton
        size="sm"
        :disabled="busy || !has_transcript || !subtitles.length"
        data-tip="translate what is missing and rebuild every subtitle file"
        @click="buildTracks(all_ids)"
      >
        build all
      </UiButton>
    </template>

    <div class="subs">
      <div class="subs__top">
        <TrackRail />

        <div
          v-if="current_track"
          class="track"
        >
          <div class="track__head">
            <span class="track__title">
              {{ current_track.kind === 'source' ? 'source' : current_track.name }}
              <span class="track__code">{{ current_track.language }}</span>
            </span>
            <span class="track__buttons">
              <UiButton
                size="sm"
                variant="ghost"
                :disabled="busy"
                data-tip="build this subtitle file from its text and the current style"
                @click="buildTrack(current_track.id)"
              >
                build
              </UiButton>
              <UiButton
                size="sm"
                variant="ghost"
                :disabled="busy || !current_track.paths.subs"
                data-tip="paint this language into the picture"
                @click="burnTrack(current_track.id)"
              >
                burn
              </UiButton>
              <a
                v-if="current_track.paths.subs"
                class="track__link"
                :href="api.fileUrl(current_track.paths.subs, { download: 1 })"
                download
                data-tip="download the .ass subtitle file"
              >.ass</a>
              <UiButton
                v-if="current_track.kind !== 'source'"
                size="sm"
                :variant="confirming === current_track.id ? 'danger' : 'ghost'"
                :disabled="busy"
                data-tip="remove this subtitle and everything built from it"
                @click="remove(current_track.id)"
              >
                {{ confirming === current_track.id ? 'remove?' : '×' }}
              </UiButton>
            </span>
          </div>

          <div class="track__states">
            <span class="track__state">
              text <UiBadge :state="text_state === 'n/a' ? 'done' : text_state" />
            </span>
            <span class="track__state">
              subtitles <UiBadge :state="current_track.styled" />
            </span>
            <span class="track__state">
              video <UiBadge :state="current_track.burned" />
            </span>
            <span class="track__segments">{{ current_track.segments }} segments</span>
          </div>
        </div>

        <nav class="tabs">
          <UiButton
            v-for="item in TABS"
            :key="item.id"
            size="sm"
            variant="ghost"
            :active="tab === item.id"
            @click="tab = item.id"
          >
            {{ item.label }}
          </UiButton>
        </nav>
      </div>

      <div class="subs__body">
        <TranscriptPanel v-show="tab === 'text'" />
        <StylesPanel v-show="tab === 'style'" />
      </div>
    </div>
  </UiPanel>
</template>

<style lang="scss" scoped>
.subs {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;

  &__top {
    flex: none;
    padding: 0.5rem 0.6rem 0;
  }

  &__body {
    flex: 1;
    min-height: 0;
    overflow: auto;
    padding: 0 0.6rem 0.5rem;
  }
}

.track {
  margin-top: 0.45rem;
  border: 1px solid var(--clr-border-100);
  background: var(--clr-surface-200);
  padding: 0.4rem 0.5rem;

  &__head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.5rem;
    padding-bottom: 0.35rem;
    margin-bottom: 0.35rem;
    border-bottom: 1px solid var(--clr-border-100);
  }

  &__title {
    font-size: var(--fs-200);
    color: var(--clr-neutral-100);
    letter-spacing: 0.04em;
    display: flex;
    align-items: baseline;
    gap: 0.35rem;
    min-width: 0;
  }

  &__code {
    font-size: var(--fs-tag);
    color: var(--clr-neutral-300);
    text-transform: uppercase;
  }

  &__buttons {
    display: flex;
    align-items: center;
    gap: 0.2rem;
    flex: none;
  }

  &__link {
    font-size: var(--fs-meta);
    color: var(--clr-neutral-300);
    text-decoration: none;
    border: 1px solid transparent;
    padding: 0.3rem 0.35rem;

    &:hover {
      color: var(--clr-primary-100);
      border-color: var(--clr-border-100);
    }
  }

  &__states {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    flex-wrap: wrap;
  }

  &__state {
    display: inline-flex;
    align-items: center;
    gap: 0.25rem;
    font-size: var(--fs-meta);
    color: var(--clr-neutral-300);
  }

  &__segments {
    margin-left: auto;
    font-size: var(--fs-meta);
    color: var(--clr-neutral-300);
  }
}

.tabs {
  display: flex;
  gap: 0.25rem;
  margin-top: 0.5rem;
  border-bottom: 1px solid var(--clr-border-100);
  padding-bottom: 0.3rem;
}
</style>
