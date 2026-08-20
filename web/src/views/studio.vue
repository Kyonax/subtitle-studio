<script setup>
/*
 * Copyright (c) 2026 Cristian D. Moreno — @Kyonax
 * Distributed under the terms of MIT — see LICENSE.
 *
 * studio — the guided flow.
 *
 * The tool is three steps: a video is prepared ONCE, carries a subtitle per
 * language, and is delivered at the end. The spine across the top states all
 * three at once — state, situation, next action — and the workspace below shows
 * only the step you are on, beside a preview that never moves because every
 * step changes what it shows.
 *
 * What used to compete for attention now has one home each: progress and the
 * log live in the status bar, delivery is a step instead of a panel footer,
 * and nothing announces its state twice.
 */

import { computed, onMounted, ref } from 'vue';

import DeliverPanel from '@panels/deliver-panel.vue';
import FilePicker from '@panels/file-picker.vue';
import PreviewPanel from '@panels/preview-panel.vue';
import SourcePanel from '@panels/source-panel.vue';
import StatusBar from '@panels/status-bar.vue';
import StepSpine from '@panels/step-spine.vue';
import SubtitlesPanel from '@panels/subtitles-panel.vue';
import UiButton from '@ui/button.vue';

import {
  busy,
  error,
  health,
  refreshState,
  start,
  state,
  step,
} from '@composables/use-studio';

const picking = ref(false);

const file_name = computed(() => state.value?.name || 'no file open');
const work_dir = computed(() => state.value?.workdir || '');

const media = computed(() => {
  const transcript = state.value?.transcript;
  if (!transcript) {
    return '';
  }
  const parts = [];
  if (transcript.duration_s) {
    parts.push(`${Math.round(transcript.duration_s)}s`);
  }
  if (transcript.video) {
    parts.push(`${transcript.video.width}x${transcript.video.height}`);
  }
  if (transcript.language) {
    parts.push(transcript.language);
  }
  return parts.join(' · ');
});

onMounted(start);
</script>

<template>
  <div class="studio">
    <header class="bar">
      <div class="bar__brand">
        <span class="bar__mark">◪</span>
        <span class="bar__name">subtitle studio</span>
        <span class="bar__version">{{ health?.version || '' }}</span>
      </div>

      <div class="bar__file">
        <UiButton
          size="sm"
          @click="picking = true"
        >
          open file
        </UiButton>
        <span
          class="bar__path"
          :title="work_dir"
        >{{ file_name }}</span>
        <span
          v-if="media"
          class="bar__media"
        >{{ media }}</span>
      </div>

      <div class="bar__stats">
        <span
          class="stat"
          :class="health?.gpu ? 'is-ok' : 'is-warn'"
          :data-tip="health?.gpu || 'no nvidia card found, everything falls back to the processor'"
        >
          {{ health?.gpu ? health.gpu.split(',')[0] : 'no gpu' }}
        </span>
        <span
          class="stat"
          :class="health?.ffmpeg ? 'is-ok' : 'is-error'"
          data-tip="ffmpeg does the audio, the frames and the delivery"
        >
          ffmpeg {{ health?.ffmpeg ? 'ready' : 'missing' }}
        </span>
        <span
          class="stat"
          :class="health?.hf_token ? 'is-ok' : 'is-warn'"
          data-tip="marking who speaks needs a free Hugging Face token in HF_TOKEN"
        >
          {{ health?.hf_token ? 'speaker token loaded' : 'no speaker token' }}
        </span>
        <UiButton
          size="sm"
          variant="ghost"
          :disabled="busy"
          @click="refreshState"
        >
          reload
        </UiButton>
      </div>
    </header>

    <StepSpine />

    <p
      v-if="error"
      class="error"
    >
      {{ error }}
    </p>

    <main class="work">
      <div class="work__step">
        <SourcePanel v-show="step === 'source'" />
        <SubtitlesPanel v-show="step === 'subtitles'" />
        <DeliverPanel v-show="step === 'deliver'" />
      </div>

      <div class="work__preview">
        <PreviewPanel />
      </div>
    </main>

    <StatusBar />

    <FilePicker
      v-if="picking"
      @close="picking = false"
    />
  </div>
</template>

<style lang="scss" scoped>
.studio {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}

.bar {
  display: flex;
  align-items: center;
  gap: 1rem;
  flex-wrap: wrap;
  padding: 0.45rem 0.7rem;
  border-bottom: 1px solid var(--clr-border-100);
  background: var(--clr-surface-200);
  flex: none;

  &__brand {
    display: flex;
    align-items: baseline;
    gap: 0.45rem;
  }

  &__mark {
    color: var(--clr-primary-100);
    font-size: var(--fs-400);
    line-height: 1;
  }

  &__name {
    font-family: "Geomanist", "SpaceMono", sans-serif;
    font-weight: 700;
    letter-spacing: 0.14em;
    text-transform: lowercase;
    color: var(--clr-neutral-100);
  }

  &__version {
    font-size: var(--fs-tag);
    color: var(--clr-neutral-300);
  }

  &__file {
    display: flex;
    align-items: center;
    gap: 0.55rem;
    min-width: 0;
  }

  &__path {
    font-size: var(--fs-200);
    color: var(--clr-neutral-100);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    max-width: 20rem;
  }

  &__media {
    font-size: var(--fs-meta);
    color: var(--clr-neutral-300);
  }

  &__stats {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    margin-left: auto;
    flex-wrap: wrap;
  }
}

.stat {
  @include kyo-chip;

  padding: 0.15rem 0.4rem;
  font-size: var(--fs-tag);
  color: var(--clr-neutral-300);
  text-transform: lowercase;

  &.is-ok    { color: var(--clr-success-100); }
  &.is-warn  { color: var(--clr-warning-100); }
  &.is-error { color: var(--clr-error-100); }
}

.error {
  margin: 0;
  padding: 0.35rem 0.7rem;
  background: color-mix(in srgb, var(--clr-error-100) 14%, transparent);
  color: var(--clr-error-100);
  font-size: var(--fs-meta);
  border-bottom: 1px solid var(--clr-error-100);
  flex: none;
}

.work {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: minmax(28rem, 38rem) minmax(0, 1fr);
  gap: 0.5rem;
  padding: 0.5rem;

  &__step,
  &__preview {
    display: flex;
    min-height: 0;
    min-width: 0;

    > :deep(.ui-panel) { flex: 1; }
  }

  @include max-media-query(md) {
    grid-template-columns: minmax(0, 1fr);
    grid-auto-rows: minmax(20rem, auto);
    overflow: auto;
  }
}
</style>
