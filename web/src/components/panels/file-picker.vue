<script setup>
/*
 * Copyright (c) 2026 Cristian D. Moreno — @Kyonax
 * Distributed under the terms of MIT — see LICENSE.
 *
 * file-picker — choose the video or audio to work on.
 *
 * The browser cannot hand a real path to a local tool, so the server lists
 * directories instead: same machine, same paths the CLI would take.
 */

import { onMounted, ref } from 'vue';

import api from '@api/client';
import UiButton from '@ui/button.vue';

import { input, setInput } from '@composables/use-studio';

const emit = defineEmits(['close']);

const listing = ref(null);
const manual = ref(input.value || '');
const error = ref('');
const loading = ref(false);

const load = async (path) => {
  loading.value = true;
  error.value = '';
  try {
    listing.value = await api.browse(path);
  } catch (exc) {
    error.value = exc.message;
  } finally {
    loading.value = false;
  }
};

const choose = async (path) => {
  await setInput(path);
  emit('close');
};

const chooseManual = async () => {
  const path = manual.value.trim();
  if (path) {
    await choose(path);
  }
};

const size = (bytes) => `${(bytes / 1024 / 1024).toFixed(1)} MB`;

onMounted(() => load());
</script>

<template>
  <div
    class="picker"
    @click.self="emit('close')"
  >
    <div class="picker__box">
      <header class="picker__head">
        <h2 class="picker__title">
          open a file
        </h2>
        <UiButton
          size="sm"
          variant="ghost"
          @click="emit('close')"
        >
          close
        </UiButton>
      </header>

      <div class="picker__path">
        <UiButton
          size="sm"
          variant="ghost"
          :disabled="!listing?.parent"
          @click="load(listing.parent)"
        >
          up
        </UiButton>
        <UiButton
          size="sm"
          variant="ghost"
          @click="load(listing?.home)"
        >
          home
        </UiButton>
        <span class="picker__here">{{ listing?.path || '…' }}</span>
      </div>

      <p
        v-if="error"
        class="picker__error"
      >
        {{ error }}
      </p>

      <div class="picker__list">
        <button
          v-for="dir in listing?.dirs || []"
          :key="dir.path"
          class="entry entry--dir"
          type="button"
          @click="load(dir.path)"
        >
          <span class="entry__icon">/</span>{{ dir.name }}
        </button>
        <button
          v-for="file in listing?.files || []"
          :key="file.path"
          class="entry"
          type="button"
          @click="choose(file.path)"
        >
          <span class="entry__icon">▸</span>{{ file.name }}
          <span class="entry__size">{{ size(file.size) }}</span>
        </button>
        <p
          v-if="listing && !listing.dirs.length && !listing.files.length && !loading"
          class="picker__empty"
        >
          no media files here
        </p>
      </div>

      <footer class="picker__foot">
        <input
          v-model="manual"
          class="picker__manual"
          type="text"
          placeholder="or type a full path"
          @keydown.enter="chooseManual"
        >
        <UiButton
          size="sm"
          variant="primary"
          :disabled="!manual.trim()"
          @click="chooseManual"
        >
          open
        </UiButton>
      </footer>
    </div>
  </div>
</template>

<style lang="scss" scoped>
.picker {
  position: fixed;
  inset: 0;
  background: color-mix(in srgb, var(--clr-neutral-900) 78%, transparent);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 40;
  padding: 2rem;

  &__box {
    @include panel(var(--clr-surface-100));

    width: min(46rem, 100%);
    max-height: min(38rem, 100%);
    display: flex;
    flex-direction: column;
  }

  &__head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.5rem 0.6rem;
    border-bottom: 1px solid var(--clr-border-100);
    background: var(--clr-surface-200);
  }

  &__title {
    font-size: var(--fs-200);
    letter-spacing: 0.1em;
    text-transform: lowercase;
    color: var(--clr-neutral-100);
  }

  &__path {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    padding: 0.4rem 0.6rem;
    border-bottom: 1px solid var(--clr-border-100);
  }

  &__here {
    font-size: var(--fs-meta);
    color: var(--clr-neutral-300);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    direction: rtl;
    text-align: left;
  }

  &__list {
    flex: 1;
    overflow: auto;
    padding: 0.3rem;
    display: flex;
    flex-direction: column;
  }

  &__error {
    margin: 0;
    padding: 0.4rem 0.6rem;
    color: var(--clr-error-100);
    font-size: var(--fs-meta);
  }

  &__empty {
    margin: 0;
    padding: 0.6rem;
    color: var(--clr-neutral-300);
    font-size: var(--fs-meta);
  }

  &__foot {
    display: flex;
    gap: 0.4rem;
    padding: 0.5rem 0.6rem;
    border-top: 1px solid var(--clr-border-100);
    background: var(--clr-surface-200);
  }

  &__manual {
    flex: 1;
    background: var(--clr-neutral-500);
    border: 1px solid var(--clr-border-100);
    color: var(--clr-neutral-100);
    padding: 0.3rem 0.45rem;
    font-size: var(--fs-200);
  }
}

.entry {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  width: 100%;
  text-align: left;
  background: transparent;
  border: 0;
  color: var(--clr-neutral-200);
  padding: 0.3rem 0.45rem;
  font-size: var(--fs-200);
  cursor: pointer;

  &:hover,
  &:focus-visible {
    background: var(--clr-surface-300);
    color: var(--clr-primary-100);
  }

  &--dir { color: var(--clr-neutral-300); }

  &__icon {
    color: var(--clr-neutral-300);
    width: 0.8rem;
  }

  &__size {
    margin-left: auto;
    font-size: var(--fs-meta);
    color: var(--clr-neutral-300);
  }
}
</style>
