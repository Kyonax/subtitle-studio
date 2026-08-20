<script setup>
/*
 * Copyright (c) 2026 Cristian D. Moreno — @Kyonax
 * Distributed under the terms of MIT — see LICENSE.
 *
 * source-panel — everything about the video itself, before any subtitle exists.
 *
 * Three stages in the order they run, then who talks and in which languages.
 * Every row is the same shape (number, name, state, options, run) and every
 * explanation lives in its `?` mark, so the column reads as a list instead of
 * a wall of prose. Translating, styling and burning are NOT here: those belong
 * to a subtitle, and subtitles have their own panel.
 */

import { computed, ref } from 'vue';

import UiBadge from '@ui/badge.vue';
import UiButton from '@ui/button.vue';
import UiField from '@ui/field.vue';
import UiGroup from '@ui/group.vue';
import UiHelpMark from '@ui/help-mark.vue';
import UiPanel from '@ui/panel.vue';
import UiSwitch from '@ui/switch.vue';

import {
  busy,
  has_input,
  has_transcript,
  health,
  languages,
  options,
  renameSpeaker,
  runStage,
  setOption,
  speakers,
  stages,
  state,
} from '@composables/use-studio';

const SOURCE_STAGES = ['extract', 'transcribe', 'diarize'];

const open_options = ref('');
const drafts = ref({});

const rows = computed(() => stages.value.filter((stage) => SOURCE_STAGES.includes(stage.id)));

const canRun = (stage) => {
  if (!has_input.value || busy.value) {
    return false;
  }
  return stage.id === 'extract' || stage.id === 'transcribe' || has_transcript.value;
};

const badgeState = (stage) => (stage.running ? 'working' : stage.state);

const nameFor = (speaker) => (drafts.value[speaker.id] ?? speaker.name ?? '');

const commitName = async (speaker) => {
  const name = (drafts.value[speaker.id] ?? '').trim();
  if (!name || name === speaker.name) {
    delete drafts.value[speaker.id];
    return;
  }
  if (await renameSpeaker(speaker.id, name)) {
    delete drafts.value[speaker.id];
  }
};
</script>

<template>
  <UiPanel
    title="source"
    :hint="state?.workdir ? state.workdir.split('/').slice(-1)[0] : 'no job yet'"
  >
    <template #actions>
      <UiButton
        size="sm"
        variant="primary"
        :disabled="!has_input || busy"
        data-tip="every stage in one go for the selected subtitle: audio, text, speakers, subtitle file"
        @click="runStage('run')"
      >
        run every stage
      </UiButton>
    </template>

    <ol class="stages">
      <li
        v-for="stage in rows"
        :key="stage.id"
        class="stage"
        :class="{ 'is-running': stage.running }"
      >
        <div class="stage__row">
          <span class="stage__number">{{ stage.number }}</span>
          <span class="stage__title">{{ stage.title }}</span>
          <UiHelpMark :tip="stage.help" />
          <UiBadge
            :state="badgeState(stage)"
            :label="stage.detail && stage.state === 'done' ? stage.detail : ''"
          />
          <span class="stage__buttons">
            <UiButton
              size="sm"
              variant="ghost"
              :active="open_options === stage.id"
              data-tip="options for this stage"
              @click="open_options = open_options === stage.id ? '' : stage.id"
            >
              ···
            </UiButton>
            <UiButton
              size="sm"
              :disabled="!canRun(stage)"
              @click="runStage(stage.id)"
            >
              run
            </UiButton>
          </span>
        </div>

        <div
          v-if="open_options === stage.id"
          class="stage__options"
        >
          <template v-if="stage.id === 'transcribe'">
            <UiField
              label="language"
              tip="auto detects it. force one (es, en) when the audio starts in another language than it continues."
            >
              <input
                :value="options.language"
                type="text"
                placeholder="auto"
                @change="setOption('language', $event.target.value)"
              >
            </UiField>
            <UiField
              label="model"
              tip="empty keeps the configured large-v3, the most accurate one that fits the card"
            >
              <input
                :value="options.model"
                type="text"
                placeholder="large-v3"
                @change="setOption('model', $event.target.value)"
              >
            </UiField>
            <UiField
              label="batch"
              tip="lower it if the card runs out of memory during transcription"
            >
              <input
                :value="options.batch"
                type="number"
                min="1"
                placeholder="8"
                @change="setOption('batch', $event.target.value)"
              >
            </UiField>
          </template>

          <template v-else-if="stage.id === 'diarize'">
            <UiField
              label="min speakers"
              tip="leave empty and it decides by itself"
            >
              <input
                :value="options.min_speakers"
                type="number"
                min="1"
                @change="setOption('min_speakers', $event.target.value)"
              >
            </UiField>
            <UiField label="max speakers">
              <input
                :value="options.max_speakers"
                type="number"
                min="1"
                @change="setOption('max_speakers', $event.target.value)"
              >
            </UiField>
            <UiField
              row
              label="skip in run"
              tip="run everything without the speaker stage"
            >
              <UiSwitch
                :model-value="options.no_diarize"
                label="skip speakers"
                @update:model-value="setOption('no_diarize', $event)"
              />
            </UiField>
          </template>

          <p
            v-else
            class="stage__note"
          >
            this stage takes no options
          </p>
        </div>
      </li>
    </ol>

    <UiGroup
      v-if="has_transcript"
      label="voices"
      columns="100%"
    >
      <template #actions>
        <UiButton
          size="sm"
          variant="ghost"
          :disabled="busy"
          data-tip="detect the language of every segment again"
          @click="runStage('languages')"
        >
          re-check
        </UiButton>
      </template>

      <p
        v-if="!speakers.length"
        class="voices__empty"
      >
        no speakers marked yet, stage 2 needs a free Hugging Face token
        <span :class="health?.hf_token ? 'is-ok' : 'is-warn'">
          ({{ health?.hf_token ? 'a token is loaded' : 'none found in HF_TOKEN' }})
        </span>
      </p>

      <ul
        v-else
        class="voices"
      >
        <li
          v-for="speaker in speakers"
          :key="speaker.id"
          class="voices__row"
        >
          <span class="voices__id">{{ speaker.id }}</span>
          <input
            class="voices__name"
            type="text"
            :value="nameFor(speaker)"
            placeholder="give them a name"
            @input="drafts[speaker.id] = $event.target.value"
            @keydown.enter="commitName(speaker)"
            @blur="commitName(speaker)"
          >
          <span class="voices__time">{{ speaker.talk_time_s }}s</span>
        </li>
      </ul>

      <ul
        v-if="languages.length"
        class="langs"
      >
        <li
          v-for="language in languages"
          :key="language.code"
          class="langs__item"
        >
          <span class="langs__code kyo-chip">{{ language.code }}</span>
          <span class="langs__stat">{{ language.segments }} segments · {{ language.talk_time_s }}s</span>
        </li>
      </ul>
    </UiGroup>
  </UiPanel>
</template>

<style lang="scss" scoped>
.stages {
  list-style: none;
  margin: 0 0 0.6rem;
  padding: 0;
}

.stage {
  border-bottom: 1px solid color-mix(in srgb, var(--clr-border-100) 45%, transparent);
  padding: 0.3rem 0;

  &:last-child { border-bottom: 0; }

  &.is-running {
    background: color-mix(in srgb, var(--clr-primary-100) 6%, transparent);
  }

  &__row {
    display: flex;
    align-items: center;
    gap: 0.4rem;
  }

  &__number {
    font-size: var(--fs-meta);
    color: var(--clr-neutral-300);
    width: 0.9rem;
    flex: none;
    text-align: right;
  }

  &__title {
    flex: 1;
    min-width: 0;
    font-size: var(--fs-200);
    color: var(--clr-neutral-100);
    letter-spacing: 0.04em;
  }

  &__buttons {
    display: flex;
    gap: 0.2rem;
    flex: none;
  }

  &__options {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(9rem, 1fr));
    gap: 0 0.7rem;
    padding: 0.2rem 0 0.3rem 1.3rem;
  }

  &__note {
    margin: 0;
    font-size: var(--fs-meta);
    color: var(--clr-neutral-300);
  }
}

.voices {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.25rem;

  &__empty {
    margin: 0;
    font-size: var(--fs-meta);
    line-height: 1.5;
    color: var(--clr-neutral-300);

    .is-ok { color: var(--clr-success-100); }
    .is-warn { color: var(--clr-warning-100); }
  }

  &__row {
    display: grid;
    grid-template-columns: 5.5rem 1fr auto;
    align-items: center;
    gap: 0.4rem;
  }

  &__id {
    font-size: var(--fs-meta);
    color: var(--clr-neutral-300);
    overflow: hidden;
    text-overflow: ellipsis;
  }

  &__name {
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

  &__time {
    font-size: var(--fs-meta);
    color: var(--clr-neutral-300);
  }
}

.langs {
  list-style: none;
  margin: 0.5rem 0 0;
  padding: 0;
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;

  &__item {
    display: inline-flex;
    align-items: center;
    gap: 0.3rem;
  }

  &__code {
    color: var(--clr-primary-100);
    padding: 0.1rem 0.3rem;
    font-size: var(--fs-meta);
  }

  &__stat {
    font-size: var(--fs-meta);
    color: var(--clr-neutral-300);
  }
}

.hint {
  margin: 0;
  font-size: var(--fs-tag);
  color: var(--clr-neutral-300);
  line-height: 1.4;

  &__lead {
    color: var(--clr-primary-100);
    letter-spacing: 0.1em;
    margin-right: 0.35rem;
  }
}
</style>
