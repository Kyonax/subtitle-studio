<script setup>
/*
 * Copyright (c) 2026 Cristian D. Moreno — @Kyonax
 * Distributed under the terms of MIT — see LICENSE.
 *
 * status-bar — one line for everything that is happening.
 *
 * The log used to hold half a column while saying nothing most of the time.
 * Here it is one line — idle, or the running stage with its progress — and the
 * full stream opens on request. What was produced sits on the right as chips
 * you can open, because that is what the work was for.
 */

import { computed, ref } from 'vue';

import api from '@api/client';
import UiButton from '@ui/button.vue';

import LogPanel from '@panels/log-panel.vue';

import {
  connection,
  delivery,
  job,
  logs,
  next_hint,
  state,
} from '@composables/use-studio';

const open = ref(false);

const last_line = computed(() => {
  for (let i = logs.value.length - 1; i >= 0; i -= 1) {
    const line = logs.value[i];
    if (line.level === 'ok' || line.level === 'error') {
      return line;
    }
  }
  return logs.value[logs.value.length - 1] || null;
});

const percent = computed(() => Math.round(Math.min(Math.max(job.value?.fraction || 0, 0), 1) * 100));
const render_path = computed(() => state.value?.artifacts?.render || '');
</script>

<template>
  <div class="status">
    <div
      v-if="open"
      class="status__drawer"
    >
      <LogPanel />
    </div>

    <div class="status__bar">
      <span
        class="status__dot"
        :class="job ? 'is-working' : 'is-idle'"
      />
      <span class="status__mode">{{ job ? job.label : 'idle' }}</span>

      <template v-if="job">
        <span class="status__sep">|</span>
        <span class="status__line">{{ job.message || 'starting' }}</span>
        <span class="status__track">
          <span
            class="status__fill"
            :class="{ 'is-unknown': !job.fraction }"
            :style="job.fraction ? { width: `${percent}%` } : null"
          />
        </span>
        <span
          v-if="job.fraction"
          class="status__percent"
        >{{ percent }}%</span>
      </template>

      <template v-else>
        <span class="status__sep">|</span>
        <span class="status__line">{{ last_line ? last_line.message : next_hint }}</span>
      </template>

      <span class="status__right">
        <a
          v-if="delivery?.path"
          class="status__chip"
          :href="api.fileUrl(delivery.path, { download: 1 })"
          download
        >subtitled.mkv</a>
        <a
          v-if="render_path"
          class="status__chip"
          :href="api.fileUrl(render_path, { download: 1 })"
          download
        >{{ render_path.split('/').slice(-1)[0] }}</a>
        <span
          class="status__conn"
          :class="connection === 'live' ? 'is-live' : 'is-off'"
        >{{ connection === 'live' ? 'live' : connection }}</span>
        <UiButton
          size="sm"
          variant="ghost"
          :active="open"
          @click="open = !open"
        >
          {{ open ? 'hide log' : 'show log' }}
        </UiButton>
      </span>
    </div>
  </div>
</template>

<style lang="scss" scoped>
.status {
  flex: none;
  display: flex;
  flex-direction: column;
  border-top: 1px solid var(--clr-border-100);
  background: var(--clr-surface-200);

  &__drawer {
    height: 15rem;
    border-bottom: 1px solid var(--clr-border-100);
    display: flex;

    > :deep(.ui-panel) { flex: 1; border: 0; }
  }

  &__bar {
    display: flex;
    align-items: center;
    gap: 0.55rem;
    padding: 0.45rem 0.8rem;
    font-size: var(--fs-meta);
    color: var(--clr-neutral-300);
  }

  &__dot {
    width: 0.45rem;
    height: 0.45rem;
    flex: none;

    &.is-idle { background: var(--clr-success-100); }
    &.is-working { background: var(--clr-primary-100); }
  }

  &__mode { color: var(--clr-neutral-200); }

  &__sep { color: var(--clr-neutral-400); }

  &__line {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    max-width: 46rem;
  }

  &__track {
    width: 9rem;
    height: 3px;
    background: var(--clr-surface-300);
    flex: none;
    overflow: hidden;
  }

  &__fill {
    display: block;
    height: 100%;
    background: var(--clr-primary-100);
    transition: width 0.2s var(--ease-standard);

    &.is-unknown {
      width: 35%;
      background: repeating-linear-gradient(
        90deg,
        var(--clr-primary-100) 0 0.5rem,
        transparent 0.5rem 1rem
      );
      animation: kyo-stripe 0.7s linear infinite;
    }
  }

  &__percent { color: var(--clr-primary-100); }

  &__right {
    margin-left: auto;
    display: flex;
    align-items: center;
    gap: 0.4rem;
  }

  &__chip {
    @include kyo-chip;

    padding: 0.15rem 0.4rem;
    font-size: var(--fs-tag);
    color: var(--clr-neutral-200);
    text-decoration: none;

    &:hover { color: var(--clr-primary-100); }
  }

  &__conn {
    font-size: var(--fs-tag);
    letter-spacing: 0.08em;

    &.is-live { color: var(--clr-success-100); }
    &.is-off { color: var(--clr-warning-100); }
  }
}
</style>
