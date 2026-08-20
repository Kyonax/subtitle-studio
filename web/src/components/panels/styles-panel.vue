<script setup>
/*
 * Copyright (c) 2026 Cristian D. Moreno — @Kyonax
 * Distributed under the terms of MIT — see LICENSE.
 *
 * styles-panel — the look of the selected subtitle, with the preview following.
 *
 * Every control is the same widget (label, `?`, control) inside a titled band,
 * so a wall of thirty settings still reads as five decisions. Writes go one key
 * at a time through tomlkit, which is why styles.toml keeps its comments and
 * stays the reference it was written to be. With a preset selected the edits
 * land in that preset's table; a preset only lists what differs from
 * [default], and the switch sends them to [default] instead.
 *
 * Position never lives in the file — it is chosen per run, like --position.
 */

import { computed, ref, watch } from 'vue';

import UiButton from '@ui/button.vue';
import UiField from '@ui/field.vue';
import UiGroup from '@ui/group.vue';
import UiPanel from '@ui/panel.vue';
import UiSwitch from '@ui/switch.vue';

import {
  options,
  presetAction,
  refreshStyles,
  saveStylesRaw,
  setOption,
  setStyleValue,
  styles,
} from '@composables/use-studio';

const mode = ref('form');
const write_to_default = ref(false);
const raw_draft = ref('');
const raw_dirty = ref(false);
const new_preset = ref('');
const custom_position = ref('');

const effective = computed(() => styles.value?.effective || {});
const target_table = computed(() => (
  options.preset && !write_to_default.value ? `style.${options.preset}` : 'default'
));

watch(() => styles.value?.raw, (value) => {
  if (!raw_dirty.value) {
    raw_draft.value = value || '';
  }
}, { immediate: true });

const read = (path) => path.split('.').reduce((node, key) => (node ? node[key] : undefined), effective.value);
const write = (path, value) => setStyleValue(target_table.value, path, value);

const writeNumber = (path, value, integer = false) => {
  const parsed = integer ? Number.parseInt(value, 10) : Number.parseFloat(value);
  if (!Number.isNaN(parsed)) {
    write(path, parsed);
  }
};

/* Colors are "#RRGGBB" or "#RRGGBBAA" — AA is opacity. The picker edits the
   visible half and keeps whatever alpha the value already carried. */
const rgbOf = (path) => (read(path) || '#000000').slice(0, 7);
const alphaOf = (path) => (read(path) || '').slice(7, 9);
const writeColor = (path, rgb) => write(path, `${rgb}${alphaOf(path)}`);

/* A subtitle is capped twice, by characters (line length x lines) and by
   words. The smaller cap wins, which is the one trap in this panel. Fitting W
   words needs at least 2W-1 characters, so anything above that is unreachable
   and the page says so instead of looking broken. */
const char_cap = computed(() => (read('max_line_chars') || 0) * (read('max_lines') || 0));
const word_cap = computed(() => read('max_words') || 0);
const words_unreachable = computed(() => word_cap.value > 0 && (2 * word_cap.value - 1) > char_cap.value);

const cap_note = computed(() => {
  if (!char_cap.value) {
    return '';
  }
  const chars = `${char_cap.value} characters (${read('max_line_chars')} x ${read('max_lines')} lines)`;
  if (!word_cap.value) {
    return `each subtitle stops at ${chars}. no word cap is set.`;
  }
  if (words_unreachable.value) {
    return `${chars} cannot hold ${word_cap.value} words, so the word cap never applies — `
      + 'raise line length or lines, or lower words per subtitle.';
  }
  return `each subtitle stops at whichever comes first, ${chars} or ${word_cap.value} words.`;
});

const positions = computed(() => styles.value?.anchors || []);

const applyPosition = (value) => {
  setOption('position', value);
  custom_position.value = '';
};

const applyCustomPosition = () => {
  const value = custom_position.value.trim();
  if (/^\d+\s*,\s*\d+$/.test(value)) {
    setOption('position', value.replace(/\s+/g, ''));
  }
};

const saveRaw = async () => {
  if (await saveStylesRaw(raw_draft.value)) {
    raw_dirty.value = false;
  }
};

const discardRaw = async () => {
  raw_dirty.value = false;
  await refreshStyles();
  raw_draft.value = styles.value?.raw || '';
};

const addPreset = async () => {
  const name = new_preset.value.trim();
  if (name && await presetAction(name, 'create')) {
    new_preset.value = '';
    setOption('preset', name);
  }
};

const dropPreset = async () => {
  if (options.preset) {
    await presetAction(options.preset, 'delete');
  }
};
</script>

<template>
  <UiPanel
    flat
    title=""
    :hint="styles?.path ? styles.path.split('/').slice(-1)[0] : 'built-in defaults'"
  >
    <template #actions>
      <UiButton
        size="sm"
        variant="ghost"
        :active="mode === 'form'"
        @click="mode = 'form'"
      >
        form
      </UiButton>
      <UiButton
        size="sm"
        variant="ghost"
        :active="mode === 'raw'"
        data-tip="edit the whole styles.toml by hand"
        @click="mode = 'raw'"
      >
        file
      </UiButton>
    </template>

    <p
      v-if="styles?.error"
      class="warning"
    >
      {{ styles.error }}
    </p>

    <template v-if="mode === 'form'">
      <UiGroup
        label="preset"
        columns="8rem"
        :note="`writing to [${target_table}]`"
      >
        <UiField
          label="use"
          tip="a preset is a named set of differences from the default look, picked per run"
        >
          <select
            :value="options.preset"
            @change="setOption('preset', $event.target.value)"
          >
            <option value="">
              (default look)
            </option>
            <option
              v-for="name in styles?.presets || []"
              :key="name"
              :value="name"
            >
              {{ name }}
            </option>
          </select>
        </UiField>

        <UiField
          label="new preset"
          tip="creates an empty [style.NAME] table, then every edit you make lands in it"
        >
          <input
            v-model="new_preset"
            type="text"
            placeholder="name"
            @keydown.enter="addPreset"
          >
          <UiButton
            size="sm"
            :disabled="!new_preset.trim()"
            @click="addPreset"
          >
            add
          </UiButton>
        </UiField>

        <UiField
          v-if="options.preset"
          row
          label="edit [default]"
          tip="send these edits to the base look instead of the preset"
        >
          <UiSwitch
            v-model="write_to_default"
            label="write to default"
          />
        </UiField>

        <UiField
          v-if="options.preset"
          row
          label="delete preset"
        >
          <UiButton
            size="sm"
            variant="danger"
            @click="dropPreset"
          >
            delete
          </UiButton>
        </UiField>
      </UiGroup>

      <UiGroup label="text">
        <UiField
          label="font"
          tip="family name, or the file stem of a font dropped into fonts/"
        >
          <input
            :value="read('font')"
            type="text"
            @change="write('font', $event.target.value)"
          >
        </UiField>
        <UiField
          label="size"
          tip="letter height in pixels, 56 reads well on 1080p"
        >
          <input
            :value="read('size')"
            type="number"
            min="8"
            max="200"
            @change="writeNumber('size', $event.target.value, true)"
          >
        </UiField>
        <UiField
          label="color"
          tip="the letter fill. the last two hex digits are opacity when you type them."
        >
          <input
            :value="rgbOf('color')"
            type="color"
            @change="writeColor('color', $event.target.value)"
          >
          <input
            :value="read('color')"
            type="text"
            @change="write('color', $event.target.value)"
          >
        </UiField>
        <UiField
          row
          label="bold"
        >
          <UiSwitch
            :model-value="read('bold')"
            label="bold"
            @update:model-value="write('bold', $event)"
          />
        </UiField>
        <UiField
          row
          label="italic"
          tip="slanted letters, harder to read at subtitle size"
        >
          <UiSwitch
            :model-value="read('italic')"
            label="italic"
            @update:model-value="write('italic', $event)"
          />
        </UiField>
        <UiField
          row
          label="all caps"
        >
          <UiSwitch
            :model-value="read('uppercase')"
            label="all caps"
            @update:model-value="write('uppercase', $event)"
          />
        </UiField>
        <UiField
          label="letter spacing"
          tip="extra pixels between letters, 0 is the font's natural spacing"
        >
          <input
            :value="read('letter_spacing')"
            type="number"
            step="0.5"
            @change="writeNumber('letter_spacing', $event.target.value)"
          >
        </UiField>
        <UiField
          label="width %"
          tip="horizontal stretch, 100 is undistorted"
        >
          <input
            :value="read('scale_x')"
            type="number"
            min="10"
            max="300"
            @change="writeNumber('scale_x', $event.target.value, true)"
          >
        </UiField>
        <UiField
          label="height %"
          tip="vertical stretch, 100 is undistorted"
        >
          <input
            :value="read('scale_y')"
            type="number"
            min="10"
            max="300"
            @change="writeNumber('scale_y', $event.target.value, true)"
          >
        </UiField>
      </UiGroup>

      <UiGroup label="outline and light">
        <UiField
          row
          label="stroke"
          tip="a dark outline around each letter keeps light text readable over any footage"
        >
          <UiSwitch
            :model-value="read('stroke.enabled')"
            label="stroke"
            @update:model-value="write('stroke.enabled', $event)"
          />
        </UiField>
        <UiField label="stroke color">
          <input
            :value="rgbOf('stroke.color')"
            type="color"
            @change="writeColor('stroke.color', $event.target.value)"
          >
        </UiField>
        <UiField label="stroke width">
          <input
            :value="read('stroke.width')"
            type="number"
            step="0.5"
            min="0"
            @change="writeNumber('stroke.width', $event.target.value)"
          >
        </UiField>

        <UiField
          row
          label="glow"
          tip="a blurred halo under the text, drawn as its own layer"
        >
          <UiSwitch
            :model-value="read('glow.enabled')"
            label="glow"
            @update:model-value="write('glow.enabled', $event)"
          />
        </UiField>
        <UiField label="glow color">
          <input
            :value="rgbOf('glow.color')"
            type="color"
            @change="writeColor('glow.color', $event.target.value)"
          >
        </UiField>
        <UiField label="glow blur">
          <input
            :value="read('glow.radius')"
            type="number"
            step="0.5"
            min="0"
            @change="writeNumber('glow.radius', $event.target.value)"
          >
        </UiField>

        <UiField
          row
          label="shadow"
          tip="a drop shadow down and right, usually unnecessary when a box is on"
        >
          <UiSwitch
            :model-value="read('shadow.enabled')"
            label="shadow"
            @update:model-value="write('shadow.enabled', $event)"
          />
        </UiField>
        <UiField label="shadow color">
          <input
            :value="rgbOf('shadow.color')"
            type="color"
            @change="writeColor('shadow.color', $event.target.value)"
          >
        </UiField>
        <UiField label="shadow offset">
          <input
            :value="read('shadow.offset')"
            type="number"
            step="0.5"
            @change="writeNumber('shadow.offset', $event.target.value)"
          >
        </UiField>
      </UiGroup>

      <UiGroup label="box behind the text">
        <UiField
          row
          label="box"
          tip="a filled plate behind the words, the most reliable way to stay readable"
        >
          <UiSwitch
            :model-value="read('background.enabled')"
            label="box"
            @update:model-value="write('background.enabled', $event)"
          />
        </UiField>
        <UiField
          label="box color"
          tip="the last two hex digits are opacity, 00 invisible, FF solid"
          span
        >
          <input
            :value="rgbOf('background.color')"
            type="color"
            @change="writeColor('background.color', $event.target.value)"
          >
          <input
            :value="read('background.color')"
            type="text"
            @change="write('background.color', $event.target.value)"
          >
        </UiField>
        <UiField
          row
          label="rounded"
          tip="draws a measured pill sized to the real glyphs instead of a square plate"
        >
          <UiSwitch
            :model-value="read('background.rounded')"
            label="rounded"
            @update:model-value="write('background.rounded', $event)"
          />
        </UiField>
        <UiField label="corner radius">
          <input
            :value="read('background.radius')"
            type="number"
            step="1"
            min="0"
            @change="writeNumber('background.radius', $event.target.value)"
          >
        </UiField>
        <UiField label="padding x">
          <input
            :value="read('background.padding.x')"
            type="number"
            min="0"
            @change="writeNumber('background.padding.x', $event.target.value, true)"
          >
        </UiField>
        <UiField label="padding y">
          <input
            :value="read('background.padding.y')"
            type="number"
            min="0"
            @change="writeNumber('background.padding.y', $event.target.value, true)"
          >
        </UiField>
        <UiField
          label="square mode"
          tip="one box around the whole text, or one box per line"
        >
          <select
            :value="read('background.mode')"
            @change="write('background.mode', $event.target.value)"
          >
            <option value="box">
              box
            </option>
            <option value="opaque-per-line">
              opaque-per-line
            </option>
          </select>
        </UiField>
      </UiGroup>

      <UiGroup label="placement and wrapping">
        <UiField
          label="position"
          tip="chosen per run, never stored in the file"
        >
          <select
            :value="positions.includes(options.position) ? options.position : ''"
            @change="applyPosition($event.target.value)"
          >
            <option
              v-for="anchor in positions"
              :key="anchor"
              :value="anchor"
            >
              {{ anchor }}
            </option>
            <option value="">
              exact x,y
            </option>
          </select>
        </UiField>
        <UiField
          label="exact x,y"
          tip="pixels in the video's own coordinate space, overrides the anchor"
        >
          <input
            v-model="custom_position"
            type="text"
            :placeholder="options.position.includes(',') ? options.position : '960,540'"
            @change="applyCustomPosition"
          >
        </UiField>
        <UiField
          label="margin left"
          tip="distance to the frame edge in pixels"
        >
          <input
            :value="read('margin.left')"
            type="number"
            min="0"
            @change="writeNumber('margin.left', $event.target.value, true)"
          >
        </UiField>
        <UiField label="margin right">
          <input
            :value="read('margin.right')"
            type="number"
            min="0"
            @change="writeNumber('margin.right', $event.target.value, true)"
          >
        </UiField>
        <UiField label="margin vertical">
          <input
            :value="read('margin.vertical')"
            type="number"
            min="0"
            @change="writeNumber('margin.vertical', $event.target.value, true)"
          >
        </UiField>
        <UiField
          label="line length"
          tip="characters before the text wraps, 42 is the subtitle habit"
        >
          <input
            :value="read('max_line_chars')"
            type="number"
            min="1"
            @change="writeNumber('max_line_chars', $event.target.value, true)"
          >
        </UiField>
        <UiField
          label="lines at once"
          tip="more text than this becomes the next timed subtitle"
        >
          <input
            :value="read('max_lines')"
            type="number"
            min="1"
            max="5"
            @change="writeNumber('max_lines', $event.target.value, true)"
          >
        </UiField>
        <UiField
          label="words per subtitle"
          tip="a ceiling, not a target: 0 is no cap, 3 or 4 suits vertical clips"
        >
          <input
            :value="read('max_words')"
            type="number"
            min="0"
            @change="writeNumber('max_words', $event.target.value, true)"
          >
        </UiField>

        <p
          v-if="cap_note"
          class="cap-note"
          :class="{ 'is-warn': words_unreachable }"
        >
          {{ cap_note }}
        </p>
      </UiGroup>
    </template>

    <div
      v-else
      class="raw"
    >
      <textarea
        v-model="raw_draft"
        class="raw__editor"
        spellcheck="false"
        @input="raw_dirty = true"
      />
      <div class="raw__tools">
        <UiButton
          size="sm"
          variant="primary"
          :disabled="!raw_dirty"
          @click="saveRaw"
        >
          save file
        </UiButton>
        <UiButton
          size="sm"
          variant="ghost"
          :disabled="!raw_dirty"
          @click="discardRaw"
        >
          discard
        </UiButton>
        <span class="raw__path">{{ styles?.path }}</span>
      </div>
    </div>
  </UiPanel>
</template>

<style lang="scss" scoped>
.warning {
  border: 1px solid var(--clr-warning-100);
  color: var(--clr-warning-100);
  padding: 0.35rem 0.5rem;
  font-size: var(--fs-meta);
  margin: 0 0 0.6rem;
}

.cap-note {
  grid-column: 1 / -1;
  margin: 0.4rem 0 0;
  font-size: var(--fs-meta);
  line-height: 1.4;
  color: var(--clr-neutral-300);
  border-left: 2px solid var(--clr-border-100);
  padding-left: 0.5rem;

  &.is-warn {
    color: var(--clr-warning-100);
    border-left-color: var(--clr-warning-100);
  }
}

.raw {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  height: 100%;

  &__editor {
    flex: 1;
    min-height: 20rem;
    resize: vertical;
    background: var(--clr-neutral-500);
    border: 1px solid var(--clr-border-100);
    color: var(--clr-neutral-100);
    padding: 0.5rem;
    font-family: "SpaceMono", monospace;
    font-size: var(--fs-200);
    line-height: 1.5;
    white-space: pre;
    overflow-wrap: normal;
    overflow-x: auto;

    &:focus-visible {
      border-color: var(--clr-primary-100);
      outline: none;
    }
  }

  &__tools {
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  &__path {
    font-size: var(--fs-meta);
    color: var(--clr-neutral-300);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
}
</style>
