<script setup>
/*
 * Copyright (c) 2026 Cristian D. Moreno — @Kyonax
 * Distributed under the terms of MIT — see LICENSE.
 *
 * preview-panel — what the subtitles actually look like.
 *
 * With a transcript the frame is a real frame of the video, taken at the
 * midpoint of the selected row's FIRST on-screen chunk and rendered through the
 * same layout engine that writes the burned subtitles. Without one it is the
 * sample-text card, so a look can be judged before anything is transcribed.
 * Either way: what is previewed is what burns.
 */

import { computed, ref } from 'vue';

import api from '@api/client';
import UiButton from '@ui/button.vue';
import UiPanel from '@ui/panel.vue';

import {
  has_transcript,
  options,
  preview,
  refreshPreview,
  schedulePreview,
  segments,
  selectSegment,
  selected_segment,
  state,
} from '@composables/use-studio';

const show_render = ref(true);

const render_path = computed(() => state.value?.artifacts?.render || '');
const render_url = computed(() => (render_path.value
  ? api.fileUrl(render_path.value, { t: state.value?.artifacts?.render_mtime || 0 })
  : ''));
const subs_path = computed(() => state.value?.artifacts?.subs || '');

const caption = computed(() => {
  if (preview.mode === 'sample') {
    return 'sample text, no video needed';
  }
  const parts = [];
  if (preview.segment !== null && preview.segment !== '') {
    parts.push(`segment ${preview.segment}`);
  }
  if (preview.at !== null) {
    parts.push(`frame at ${preview.at.toFixed(2)}s`);
  }
  if (options.preset) {
    parts.push(`preset ${options.preset}`);
  }
  parts.push(options.position);
  return parts.join(' · ');
});

const step = (direction) => {
  const list = segments.value;
  if (!list.length) {
    return;
  }
  const index = list.findIndex((segment) => segment.id === selected_segment.value);
  const next = Math.min(Math.max((index === -1 ? 0 : index) + direction, 0), list.length - 1);
  selectSegment(list[next].id);
};

const toggleSample = () => {
  preview.sample = !preview.sample;
  schedulePreview(true);
};

const toggleZoom = () => {
  preview.zoom = preview.zoom === 'fit' ? 'full' : 'fit';
};

const openFullSize = () => {
  if (preview.url) {
    window.open(preview.url, '_blank', 'noopener');
  }
};
</script>

<template>
  <UiPanel
    title="preview"
    :hint="caption"
    :pad="false"
  >
    <template #actions>
      <UiButton
        size="sm"
        variant="ghost"
        :disabled="!segments.length || preview.sample"
        title="previous segment"
        @click="step(-1)"
      >
        ‹
      </UiButton>
      <UiButton
        size="sm"
        variant="ghost"
        :disabled="!segments.length || preview.sample"
        title="next segment"
        @click="step(1)"
      >
        ›
      </UiButton>
      <UiButton
        size="sm"
        variant="ghost"
        :active="preview.sample"
        :disabled="!has_transcript"
        title="show the sample-text card instead of a real frame"
        @click="toggleSample"
      >
        sample
      </UiButton>
      <UiButton
        size="sm"
        variant="ghost"
        :active="preview.zoom === 'full'"
        title="fit the pane or show the frame at full size"
        @click="toggleZoom"
      >
        {{ preview.zoom === 'fit' ? 'fit' : 'full' }}
      </UiButton>
      <UiButton
        size="sm"
        variant="ghost"
        title="open this frame in a new tab"
        :disabled="!preview.url"
        @click="openFullSize"
      >
        open
      </UiButton>
      <UiButton
        size="sm"
        :disabled="preview.loading"
        @click="refreshPreview"
      >
        refresh
      </UiButton>
    </template>

    <div class="preview">
      <div
        class="preview__stage"
        :class="`is-${preview.zoom}`"
      >
        <img
          v-if="preview.url"
          :src="preview.url"
          alt="subtitle preview frame"
          class="preview__image"
        >
        <p
          v-else-if="!preview.loading"
          class="preview__empty"
        >
          no preview yet
        </p>
        <div
          v-if="preview.loading"
          class="preview__loading"
        >
          rendering preview
        </div>
      </div>

      <p
        v-if="preview.error"
        class="preview__error"
      >
        {{ preview.error }}
      </p>

      <div
        v-if="render_url"
        class="render"
      >
        <div class="render__head">
          <UiButton
            size="sm"
            variant="ghost"
            :active="show_render"
            @click="show_render = !show_render"
          >
            {{ show_render ? 'hide' : 'show' }} burned video
          </UiButton>
          <a
            class="render__link"
            :href="api.fileUrl(render_path, { download: 1 })"
            download
          >download</a>
          <a
            v-if="subs_path"
            class="render__link"
            :href="api.fileUrl(subs_path, { download: 1 })"
            download
          >subtitle file</a>
        </div>
        <video
          v-if="show_render"
          :key="render_url"
          class="render__player"
          controls
          preload="metadata"
          :src="render_url"
        />
      </div>
    </div>
  </UiPanel>
</template>

<style lang="scss" scoped>
.preview {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;

  &__stage {
    position: relative;
    flex: 1;
    min-height: 0;
    background:
      repeating-conic-gradient(var(--clr-surface-200) 0% 25%, var(--clr-surface-100) 0% 50%)
      50% / 1.6rem 1.6rem;
    display: flex;
    align-items: center;
    justify-content: center;

    &.is-fit {
      overflow: hidden;

      .preview__image {
        max-width: 100%;
        max-height: 100%;
        object-fit: contain;
      }
    }

    &.is-full {
      overflow: auto;
      align-items: flex-start;
      justify-content: flex-start;

      .preview__image {
        max-width: none;
        max-height: none;
      }
    }
  }

  &__image {
    display: block;
  }

  &__empty {
    color: var(--clr-neutral-300);
    font-size: var(--fs-200);
    margin: 0;
  }

  &__loading {
    position: absolute;
    inset: auto 0 0 0;
    padding: 0.3rem 0.6rem;
    background: color-mix(in srgb, var(--clr-neutral-500) 80%, transparent);
    color: var(--clr-primary-100);
    font-size: var(--fs-meta);
    letter-spacing: 0.08em;
  }

  &__error {
    margin: 0;
    padding: 0.4rem 0.6rem;
    color: var(--clr-error-100);
    font-size: var(--fs-meta);
    border-top: 1px solid var(--clr-border-100);
  }
}

.render {
  border-top: 1px solid var(--clr-border-100);
  background: var(--clr-surface-100);

  &__head {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    padding: 0.3rem 0.5rem;
  }

  &__link {
    color: var(--clr-neutral-300);
    font-size: var(--fs-meta);
    text-decoration: none;
    border-bottom: 1px solid var(--clr-border-100);

    &:hover { color: var(--clr-primary-100); }
  }

  &__player {
    width: 100%;
    max-height: 14rem;
    display: block;
    background: var(--clr-neutral-900);
  }
}
</style>
