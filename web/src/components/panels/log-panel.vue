<script setup>
/*
 * Copyright (c) 2026 Cristian D. Moreno — @Kyonax
 * Distributed under the terms of MIT — see LICENSE.
 *
 * log-panel — everything the stages said, in the order they said it.
 * The same lines the CLI prints, streamed over server-sent events.
 */

import { nextTick, ref, watch } from 'vue';

import UiButton from '@ui/button.vue';
import UiPanel from '@ui/panel.vue';

import { connection, logs } from '@composables/use-studio';

const box = ref(null);
const pinned = ref(true);

watch(() => logs.value.length, async () => {
  if (!pinned.value) {
    return;
  }
  await nextTick();
  if (box.value) {
    box.value.scrollTop = box.value.scrollHeight;
  }
});

const onScroll = () => {
  if (!box.value) {
    return;
  }
  const distance = box.value.scrollHeight - box.value.scrollTop - box.value.clientHeight;
  pinned.value = distance < 40;
};

const time = (ts) => new Date(ts).toLocaleTimeString([], { hour12: false });
</script>

<template>
  <UiPanel
    title="log"
    :hint="connection === 'live' ? 'live' : connection"
    :pad="false"
  >
    <template #actions>
      <UiButton
        size="sm"
        variant="ghost"
        :active="pinned"
        title="stick to the newest line"
        @click="pinned = !pinned"
      >
        follow
      </UiButton>
      <UiButton
        size="sm"
        variant="ghost"
        @click="logs = []"
      >
        clear
      </UiButton>
    </template>

    <div
      ref="box"
      class="log"
      @scroll="onScroll"
    >
      <p
        v-for="(line, index) in logs"
        :key="index"
        class="log__line"
        :class="`is-${line.level}`"
      >
        <span class="log__time">{{ time(line.ts) }}</span>{{ line.message }}
      </p>
      <p
        v-if="!logs.length"
        class="log__empty"
      >
        nothing has run yet
      </p>
    </div>
  </UiPanel>
</template>

<style lang="scss" scoped>
.log {
  height: 100%;
  overflow: auto;
  padding: 0.4rem 0.6rem;
  font-size: var(--fs-meta);
  line-height: 1.5;

  &__line {
    margin: 0;
    color: var(--clr-neutral-200);
    white-space: pre-wrap;
    overflow-wrap: anywhere;

    &.is-ok    { color: var(--clr-success-100); }
    &.is-warn  { color: var(--clr-warning-100); }
    &.is-error { color: var(--clr-error-100); }
    &.is-trace { color: var(--clr-neutral-300); }
  }

  &__time {
    color: var(--clr-neutral-300);
    margin-right: 0.5rem;
  }

  &__empty {
    margin: 0;
    color: var(--clr-neutral-300);
  }
}
</style>
