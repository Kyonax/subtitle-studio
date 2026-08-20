<script setup>
/*
 * Copyright (c) 2026 Cristian D. Moreno — @Kyonax
 * Distributed under the terms of MIT — see LICENSE.
 *
 * deliver-panel — step three: subtitles become a video.
 *
 * Two ways out, and they are not the same thing, so the panel says which is
 * which in plain words. EMBED writes every chosen language into one file as
 * switchable streams: the player picks the language, the styling survives, and
 * nothing is re-encoded, so it takes seconds. BURN paints ONE language into the
 * frames for good — slower, lossy, and the only thing that works where players
 * ignore subtitle streams.
 */

import { computed, ref, watch } from 'vue';

import api from '@api/client';
import UiBadge from '@ui/badge.vue';
import UiButton from '@ui/button.vue';
import UiField from '@ui/field.vue';
import UiGroup from '@ui/group.vue';
import UiPanel from '@ui/panel.vue';
import UiSwitch from '@ui/switch.vue';

import {
  burnTrack,
  busy,
  delivery,
  deliver_state,
  generateVideo,
  setTrack,
  subtitles,
  track,
} from '@composables/use-studio';

const excluded = ref(new Set());
const burn_target = ref('');

watch(subtitles, (list) => {
  const known = new Set(list.map((item) => item.id));
  [...excluded.value].forEach((id) => {
    if (!known.has(id)) {
      excluded.value.delete(id);
    }
  });
  if (!list.some((item) => item.id === burn_target.value)) {
    burn_target.value = track.value || list[0]?.id || '';
  }
}, { immediate: true, deep: true });

const built = computed(() => subtitles.value.filter((item) => item.paths?.subs));
const chosen = computed(() => built.value.filter((item) => !excluded.value.has(item.id)));

const toggle = (id, on) => {
  const next = new Set(excluded.value);
  if (on) {
    next.delete(id);
  } else {
    next.add(id);
  }
  excluded.value = next;
};

const burn_item = computed(() => subtitles.value.find((item) => item.id === burn_target.value) || null);

const burn = () => {
  setTrack(burn_target.value);
  burnTrack(burn_target.value);
};

const file_name = (path) => (path ? path.split('/').slice(-1)[0] : '');
</script>

<template>
  <UiPanel
    title="deliver"
    hint="subtitles become a video"
  >
    <UiGroup
      label="one video, every language"
      columns="100%"
      note="written as switchable subtitle streams — the viewer picks the language in their player. the picture is copied untouched, so this takes seconds and loses no quality."
    >
      <p
        v-if="!built.length"
        class="empty"
      >
        no subtitle files yet — build one in step 2 and this becomes available
      </p>

      <div
        v-else
        class="tracks"
      >
        <div
          v-for="item in built"
          :key="item.id || 'source'"
          class="tracks__row"
        >
          <UiSwitch
            :model-value="!excluded.has(item.id)"
            :label="`include ${item.name}`"
            :disabled="busy"
            @update:model-value="toggle(item.id, $event)"
          />
          <span class="tracks__name">{{ item.kind === 'source' ? 'source' : item.name }}</span>
          <span class="tracks__code">{{ item.language }}</span>
          <UiBadge :state="item.styled" />
        </div>
      </div>

      <UiButton
        variant="primary"
        size="lg"
        block
        :disabled="busy || !chosen.length"
        @click="generateVideo(chosen.map((item) => item.id))"
      >
        generate the video with {{ chosen.length }} subtitle{{ chosen.length === 1 ? '' : 's' }}
      </UiButton>

      <p class="result">
        <UiBadge :state="deliver_state" />
        <template v-if="delivery?.path">
          <a
            class="result__link"
            :href="api.fileUrl(delivery.path, { download: 1 })"
            download
          >{{ file_name(delivery.path) }}</a>
          <span class="result__hint">{{ delivery.tracks_built.length }} inside</span>
        </template>
        <span
          v-else
          class="result__hint"
        >nothing generated yet</span>
      </p>
    </UiGroup>

    <UiGroup
      label="one language, painted in"
      columns="100%"
      note="re-encoded with the card, a minute or so per video. use it where subtitle streams are ignored — social platforms, most autoplay embeds."
    >
      <UiField
        label="language to burn"
        tip="the picture is redrawn with this language's subtitles baked into it"
      >
        <select
          v-model="burn_target"
          :disabled="busy || !built.length"
        >
          <option
            v-for="item in built"
            :key="item.id || 'source'"
            :value="item.id"
          >
            {{ item.kind === 'source' ? `source (${item.language})` : item.name }}
          </option>
        </select>
      </UiField>

      <div class="burn">
        <UiButton
          :disabled="busy || !burn_item"
          @click="burn"
        >
          burn {{ burn_item ? (burn_item.kind === 'source' ? 'the source' : burn_item.name) : '' }} into the picture
        </UiButton>
        <UiBadge :state="burn_item?.burned || 'pending'" />
        <a
          v-if="burn_item?.paths?.render"
          class="result__link"
          :href="api.fileUrl(burn_item.paths.render, { download: 1 })"
          download
        >{{ file_name(burn_item.paths.render) }}</a>
      </div>
    </UiGroup>
  </UiPanel>
</template>

<style lang="scss" scoped>
.empty {
  margin: 0;
  font-size: var(--fs-meta);
  color: var(--clr-neutral-300);
}

.tracks {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  margin-bottom: 0.7rem;

  &__row {
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  &__name {
    font-size: var(--fs-200);
    color: var(--clr-neutral-100);
  }

  &__code {
    font-size: var(--fs-tag);
    color: var(--clr-neutral-300);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin-right: auto;
  }
}

.result {
  margin: 0.6rem 0 0;
  display: flex;
  align-items: center;
  gap: 0.45rem;
  flex-wrap: wrap;

  &__link {
    font-size: var(--fs-meta);
    color: var(--clr-neutral-200);
    text-decoration: none;
    border-bottom: 1px solid var(--clr-border-100);

    &:hover { color: var(--clr-primary-100); }
  }

  &__hint {
    font-size: var(--fs-meta);
    color: var(--clr-neutral-300);
  }
}

.burn {
  display: flex;
  align-items: center;
  gap: 0.45rem;
  flex-wrap: wrap;
  margin-top: 0.6rem;
}
</style>
