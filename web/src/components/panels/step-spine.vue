<script setup>
/*
 * Copyright (c) 2026 Cristian D. Moreno — @Kyonax
 * Distributed under the terms of MIT — see LICENSE.
 *
 * step-spine — the whole job in three sentences.
 *
 * Source happens once, a subtitle happens per language, delivery happens last:
 * that order IS the tool, so the page states it across the top and shows one
 * step's workspace at a time. Each segment carries its own state in one word,
 * its situation in one sentence, and the single action that moves it forward —
 * so "what do I do next" never needs hunting for.
 */

import { computed } from 'vue';

import UiBadge from '@ui/badge.vue';
import UiButton from '@ui/button.vue';

import {
  buildTrack,
  buildTracks,
  busy,
  delivery,
  generateVideo,
  has_input,
  has_transcript,
  needs_rebuild,
  runStage,
  setStep,
  STEPS,
  step,
  step_state,
  step_summary,
  subtitles,
} from '@composables/use-studio';

const all_ids = computed(() => subtitles.value.map((item) => item.id));
const built_ids = computed(() => subtitles.value.filter((item) => item.paths?.subs).map((item) => item.id));

/* One action per step. It is the thing that step is FOR — never a menu. */
const action = computed(() => {
  const stale = needs_rebuild.value;
  return {
    source: has_transcript.value
      ? { label: 're-transcribe', variant: 'secondary', run: () => go('source', 'transcribe') }
      : { label: 'transcribe this video', variant: 'primary', run: () => go('source', 'transcribe') },
    subtitles: stale.length
      ? {
        label: `rebuild ${stale[0].kind === 'source' ? 'the source subtitle' : stale[0].name}`,
        variant: 'primary',
        run: () => {
          setStep('subtitles');
          buildTrack(stale[0].id);
        },
      }
      : (subtitles.value.length > 1
        ? {
          label: 'build every subtitle',
          variant: 'secondary',
          run: () => {
            setStep('subtitles');
            buildTracks(all_ids.value);
          },
        }
        : { label: 'add a language', variant: 'primary', run: () => setStep('subtitles') }),
    deliver: {
      label: 'generate the video',
      variant: delivery.value?.state === 'done' ? 'secondary' : 'primary',
      run: () => {
        setStep('deliver');
        generateVideo(built_ids.value);
      },
    },
  };
});

const go = (id, stage) => {
  setStep(id);
  runStage(stage);
};

const enabled = (id) => {
  if (busy.value || !has_input.value) {
    return false;
  }
  if (id === 'source') {
    return true;
  }
  if (id === 'subtitles') {
    return has_transcript.value;
  }
  return built_ids.value.length > 0;
};
</script>

<template>
  <nav class="spine">
    <button
      v-for="item in STEPS"
      :key="item.id"
      type="button"
      class="step"
      :class="{ 'is-on': step === item.id }"
      @click="setStep(item.id)"
    >
      <span class="step__top">
        <span
          class="step__n"
          :class="`is-${step_state[item.id]}`"
        >{{ item.number }}</span>
        <span class="step__name">{{ item.name }}</span>
        <UiBadge
          class="step__badge"
          :state="step_state[item.id]"
        />
      </span>

      <span class="step__state">{{ step_summary[item.id] }}</span>

      <span class="step__act">
        <UiButton
          :variant="action[item.id].variant"
          size="sm"
          :disabled="!enabled(item.id)"
          @click.stop="action[item.id].run()"
        >
          {{ action[item.id].label }}
        </UiButton>
        <UiButton
          v-if="item.id === 'subtitles' && has_transcript"
          size="sm"
          variant="ghost"
          :disabled="busy"
          @click.stop="setStep('subtitles')"
        >
          add a language
        </UiButton>
        <UiButton
          v-if="item.id === 'deliver'"
          size="sm"
          variant="ghost"
          :disabled="!enabled('deliver')"
          @click.stop="setStep('deliver')"
        >
          burn one language
        </UiButton>
      </span>
    </button>
  </nav>
</template>

<style lang="scss" scoped>
.spine {
  display: flex;
  align-items: stretch;
  gap: 1px;
  background: var(--clr-border-100);
  border-bottom: 1px solid var(--clr-border-100);
  flex: none;
}

.step {
  flex: 1;
  min-width: 0;
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 0.3rem;
  padding: 0.65rem 0.9rem;
  background: var(--clr-surface-100);
  border: 0;
  text-align: left;
  font-family: inherit;
  cursor: pointer;
  transition: background 0.15s var(--ease-standard);

  &:hover { background: var(--clr-surface-200); }

  &.is-on {
    background: color-mix(in srgb, var(--clr-primary-100) 7%, var(--clr-surface-200));

    &::before {
      content: "";
      position: absolute;
      inset: 0 auto 0 0;
      width: 2px;
      background: var(--clr-primary-100);
    }
  }

  &__top {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    width: 100%;
  }

  &__n {
    width: 1.35rem;
    height: 1.35rem;
    flex: none;
    border: 1px solid var(--clr-border-100);
    color: var(--clr-neutral-300);
    font-size: var(--fs-tag);
    display: flex;
    align-items: center;
    justify-content: center;

    &.is-done { border-color: var(--clr-success-100); color: var(--clr-success-100); }
    &.is-stale { border-color: var(--clr-warning-100); color: var(--clr-warning-100); }
    &.is-working { border-color: var(--clr-primary-100); color: var(--clr-primary-100); }
  }

  &__name {
    font-family: "Geomanist", "SpaceMono", sans-serif;
    font-weight: 700;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    font-size: var(--fs-200);
    color: var(--clr-neutral-100);
  }

  &__badge { margin-left: auto; }

  &__state {
    font-size: var(--fs-meta);
    color: var(--clr-neutral-300);
    line-height: 1.4;
    overflow: hidden;
    text-overflow: ellipsis;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
  }

  &__act {
    display: flex;
    align-items: center;
    gap: 0.35rem;
    margin-top: 0.1rem;
    flex-wrap: wrap;
  }
}
</style>
