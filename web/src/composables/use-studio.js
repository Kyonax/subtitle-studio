/*
 * Copyright (c) 2026 Cristian D. Moreno — @Kyonax
 * Distributed under the terms of MIT — see LICENSE.
 *
 * use-studio.js — one shared store for the whole page.
 *
 * Module-level refs on purpose: every panel reads the same job state, so the
 * transcript, the badges and the preview can never disagree with each other.
 * The server is the only source of truth — actions send a change, then refetch.
 *
 * Preview truth (Law 4 of the edit-integrity contract): the preview is asked
 * for with the row the user is on, and the server renders it through the same
 * layout engine that builds the real subtitles. What is previewed is what burns.
 */

import { computed, reactive, ref } from 'vue';

import api from '@api/client';

const STORAGE_KEY = 'subtitle-studio.session';
const LOG_LIMIT = 500;
const PREVIEW_DEBOUNCE = 400;

export const STAGES = [
  {
    id: 'extract',
    number: 0,
    title: 'prepare audio',
    help: 'pull a clean mono track out of the file, everything else listens to it',
  },
  {
    id: 'transcribe',
    number: 1,
    title: 'transcribe',
    help: 'write the timed text, word by word, the thing every later stage uses',
  },
  {
    id: 'diarize',
    number: 2,
    title: 'identify speakers',
    help: 'mark who is talking in each part, needs a free Hugging Face token',
  },
  {
    id: 'translate',
    number: 3,
    title: 'translate',
    help: 'unify the video into one language, or cross a two-language video',
  },
  {
    id: 'style',
    number: 4,
    title: 'build subtitles',
    help: 'turn the text into the styled subtitle file, following styles.toml',
  },
  {
    id: 'render',
    number: 5,
    title: 'burn video',
    help: 'write a new video with the subtitles painted into the picture',
  },
];

const stored = (() => {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}');
  } catch {
    return {};
  }
})();

export const input = ref(stored.input || '');
export const track = ref(stored.track || '');
export const state = ref(null);
export const health = ref(null);
export const styles = ref(null);
export const logs = ref([]);
export const job = ref(null);
export const connection = ref('offline');
export const error = ref('');
export const selected_segment = ref(stored.segment ?? null);

/* The three steps the whole tool is made of. A video is prepared ONCE (source),
   carries N subtitles (one per language), and is delivered at the end — so the
   page asks for one decision at a time in that order. */
export const STEPS = [
  { id: 'source', number: 1, name: 'source' },
  { id: 'subtitles', number: 2, name: 'subtitles' },
  { id: 'deliver', number: 3, name: 'deliver' },
];

export const step = ref(stored.step || '');
let step_chosen = Boolean(stored.step);

export const options = reactive({
  language: stored.options?.language || 'auto',
  model: stored.options?.model || '',
  batch: stored.options?.batch || '',
  min_speakers: stored.options?.min_speakers || '',
  max_speakers: stored.options?.max_speakers || '',
  to: stored.options?.to || 'en',
  swap: stored.options?.swap || false,
  all: stored.options?.all || false,
  preset: stored.options?.preset || '',
  position: stored.options?.position || 'bottom-center',
  burn: stored.options?.burn || false,
  no_diarize: stored.options?.no_diarize || false,
  force: '',
  codec: stored.options?.codec || '',
  cq: stored.options?.cq || '',
});

export const preview = reactive({
  url: '',
  at: null,
  segment: null,
  mode: 'sample',
  loading: false,
  error: '',
  zoom: 'fit',
  sample: false,
  stamp: 0,
});

const persist = () => {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({
      input: input.value,
      track: track.value,
      step: step.value,
      segment: selected_segment.value,
      options: { ...options, force: '' },
    }));
  } catch {
    /* a private window without storage is not a reason to stop working */
  }
};

export const log = (message, level = 'info') => {
  logs.value.push({ message, level, ts: Date.now() });
  if (logs.value.length > LOG_LIMIT) {
    logs.value.splice(0, logs.value.length - LOG_LIMIT);
  }
};

// --------------------------------------------------------------------------
// reading the world
// --------------------------------------------------------------------------

export const refreshState = async () => {
  try {
    state.value = await api.job(input.value, track.value);
    job.value = state.value.job?.current || null;
    error.value = '';
  } catch (exc) {
    error.value = exc.message;
  }
};

export const refreshStyles = async () => {
  try {
    styles.value = await api.styles(input.value, options.preset);
  } catch (exc) {
    error.value = exc.message;
  }
};

export const refreshHealth = async () => {
  try {
    health.value = await api.health(input.value);
  } catch (exc) {
    error.value = exc.message;
  }
};

// --------------------------------------------------------------------------
// the preview
// --------------------------------------------------------------------------

let preview_timer = null;
let preview_abort = null;

export const refreshPreview = async () => {
  if (preview_abort) {
    preview_abort.abort();
  }
  preview_abort = new AbortController();
  preview.loading = true;
  preview.error = '';
  try {
    const result = await api.preview({
      input: input.value,
      track: track.value,
      preset: options.preset,
      position: options.position,
      segment: selected_segment.value,
      sample: preview.sample ? 1 : '',
    }, preview_abort.signal);
    if (preview.url) {
      URL.revokeObjectURL(preview.url);
    }
    preview.url = URL.createObjectURL(result.blob);
    preview.at = result.at;
    preview.segment = result.segment;
    preview.mode = result.mode;
    preview.stamp = Date.now();
  } catch (exc) {
    if (exc.name !== 'AbortError') {
      preview.error = exc.message;
    }
  } finally {
    preview.loading = false;
  }
};

export const schedulePreview = (immediate = false) => {
  clearTimeout(preview_timer);
  preview_timer = setTimeout(refreshPreview, immediate ? 0 : PREVIEW_DEBOUNCE);
};

// --------------------------------------------------------------------------
// acting
// --------------------------------------------------------------------------

export const setInput = async (path) => {
  input.value = path;
  track.value = '';
  selected_segment.value = null;
  persist();
  await Promise.all([refreshState(), refreshStyles(), refreshHealth()]);
  schedulePreview(true);
};

export const setTrack = async (value) => {
  track.value = value || '';
  persist();
  await refreshState();
  schedulePreview(true);
};

export const selectSegment = (id) => {
  selected_segment.value = id;
  preview.sample = false;
  persist();
  schedulePreview();
};

export const runStage = async (stage, extra = {}) => {
  error.value = '';
  try {
    const payload = { ...options, track: track.value, ...extra };
    await api.run(stage, input.value, payload);
  } catch (exc) {
    error.value = exc.message;
    log(exc.message, exc.busy ? 'warn' : 'error');
  }
};

export const saveSegment = async (id, text) => {
  try {
    await api.editSegment(input.value, track.value, id, text);
    await refreshState();
    selectSegment(id);
    schedulePreview(true);
    return true;
  } catch (exc) {
    error.value = exc.message;
    log(exc.message, 'error');
    return false;
  }
};

export const renameSpeaker = async (speaker_id, name) => {
  try {
    await api.renameSpeaker(input.value, speaker_id, name);
    await refreshState();
    schedulePreview();
    return true;
  } catch (exc) {
    error.value = exc.message;
    log(exc.message, 'error');
    return false;
  }
};

export const setStyleValue = async (table, key, value) => {
  try {
    await api.setStyle(input.value, table, key, value);
    await refreshStyles();
    schedulePreview();
    return true;
  } catch (exc) {
    error.value = exc.message;
    log(exc.message, 'error');
    await refreshStyles();
    return false;
  }
};

export const saveStylesRaw = async (raw) => {
  try {
    await api.saveStyles(input.value, raw);
    await refreshStyles();
    schedulePreview(true);
    log('styles.toml saved', 'ok');
    return true;
  } catch (exc) {
    error.value = exc.message;
    log(exc.message, 'error');
    return false;
  }
};

export const presetAction = async (name, action) => {
  try {
    await api.preset(input.value, name, action);
    if (action === 'delete' && options.preset === name) {
      options.preset = '';
    }
    await refreshStyles();
    schedulePreview();
    return true;
  } catch (exc) {
    error.value = exc.message;
    log(exc.message, 'error');
    return false;
  }
};

// --------------------------------------------------------------------------
// the subtitle tracks — one video, N languages
// --------------------------------------------------------------------------

export const addTrack = async (language) => {
  const code = String(language || '').trim().toLowerCase();
  if (!code) {
    return false;
  }
  await runStage('add_track', code === 'swap' ? { swap: true } : { to: code, swap: false });
  return true;
};

export const removeTrack = async (id) => {
  try {
    await api.removeTrack(input.value, id);
    if (track.value === id) {
      await setTrack('');
    } else {
      await refreshState();
    }
    return true;
  } catch (exc) {
    error.value = exc.message;
    log(exc.message, 'error');
    return false;
  }
};

export const buildTracks = (ids) => runStage('build_tracks', { tracks: ids });

export const buildTrack = (id) => runStage('build_tracks', { tracks: [id] });

export const burnTrack = (id) => runStage('render', { track: id });

export const generateVideo = (ids) => runStage('mux', { tracks: ids });

export const setOption = (key, value) => {
  options[key] = value;
  persist();
  if (key === 'preset' || key === 'position') {
    refreshStyles();
    schedulePreview();
  }
};

// --------------------------------------------------------------------------
// the live wire
// --------------------------------------------------------------------------

let disconnect = null;

const onEvent = (event) => {
  if (event.type === 'log') {
    log(event.message, event.level);
  } else if (event.type === 'progress') {
    if (job.value) {
      job.value = { ...job.value, message: event.message, fraction: event.fraction };
    }
  } else if (event.type === 'job') {
    job.value = event.event === 'start' ? event.job : null;
    if (event.event === 'end') {
      refreshState().then(() => schedulePreview(true));
      refreshStyles();
    }
  } else if (event.type === 'invalidate') {
    refreshState();
  } else if (event.type === 'styles') {
    refreshStyles();
    schedulePreview();
  } else if (event.type === 'trace') {
    log(event.text, 'trace');
  }
};

export const connect = () => {
  disconnect?.();
  disconnect = api.events(onEvent, (status) => {
    connection.value = status;
  });
};

export const start = async () => {
  connect();
  await refreshHealth();
  if (!input.value && health.value?.default_input) {
    input.value = health.value.default_input;
  }
  await Promise.all([refreshState(), refreshStyles()]);
  if (!step_chosen) {
    step.value = suggested_step.value;
  }
  schedulePreview(true);
};

// --------------------------------------------------------------------------
// derived
// --------------------------------------------------------------------------

export const subtitles = computed(() => state.value?.subtitles || []);
export const delivery = computed(() => state.value?.delivery || null);
export const current_track = computed(
  () => subtitles.value.find((item) => item.id === track.value) || subtitles.value[0] || null,
);
export const built_tracks = computed(() => subtitles.value.filter((item) => item.paths?.subs));

export const segments = computed(() => state.value?.transcript?.segments || []);
export const speakers = computed(() => state.value?.speakers || []);
export const languages = computed(() => state.value?.languages || []);
export const tracks = computed(() => state.value?.tracks || []);
export const busy = computed(() => Boolean(job.value));
export const has_transcript = computed(() => Boolean(state.value?.stages?.transcribe?.state === 'done'));
export const has_input = computed(() => Boolean(state.value?.exists));

export const stages = computed(() => STAGES.map((stage) => ({
  ...stage,
  ...(state.value?.stages?.[stage.id] || { state: 'pending' }),
  running: job.value?.stage === stage.id,
})));

const SOURCE_STAGES = ['extract', 'transcribe', 'diarize', 'languages', 'relisten'];
const SUBTITLE_STAGES = ['translate', 'style', 'add_track', 'build_tracks', 'run'];
const DELIVER_STAGES = ['mux', 'render'];

const running_in = (ids) => Boolean(job.value && ids.includes(job.value.stage));

const language_name = (item) => (item?.kind === 'source' ? item.name : item?.name);

export const source_state = computed(() => {
  if (running_in(SOURCE_STAGES)) {
    return 'working';
  }
  if (!has_input.value) {
    return 'pending';
  }
  return state.value?.stages?.transcribe?.state === 'done' ? 'done' : 'pending';
});

export const subtitles_state = computed(() => {
  if (running_in(SUBTITLE_STAGES)) {
    return 'working';
  }
  const list = subtitles.value;
  if (!list.length) {
    return 'pending';
  }
  if (list.some((item) => item.styled === 'stale' || item.translate === 'stale')) {
    return 'stale';
  }
  return list.every((item) => item.styled === 'done') ? 'done' : 'pending';
});

export const deliver_state = computed(() => {
  if (running_in(DELIVER_STAGES)) {
    return 'working';
  }
  return state.value?.delivery?.state || 'pending';
});

/* The stale ones, named — the spine says which language needs attention rather
   than making the owner hunt for an amber badge. */
export const needs_rebuild = computed(() => subtitles.value.filter(
  (item) => item.styled === 'stale' || item.translate === 'stale',
));

export const step_state = computed(() => ({
  source: source_state.value,
  subtitles: subtitles_state.value,
  deliver: deliver_state.value,
}));

export const step_summary = computed(() => {
  const transcript = state.value?.transcript;
  const list = subtitles.value;
  const stale = needs_rebuild.value;
  const ready = list.filter((item) => item.styled === 'done').length;
  const delivery_tracks = state.value?.delivery?.tracks_built?.length || 0;

  let source = 'open a video or audio file to start';
  if (has_input.value && source_state.value === 'pending') {
    source = 'not transcribed yet — this is where every subtitle comes from';
  } else if (transcript) {
    const voices = speakers.value.length;
    source = `transcribed — ${transcript.segments.length} segments, `
      + `${voices ? `${voices} voices` : 'voices not marked'}, ${language_name(list[0]) || transcript.language}`;
  }

  let subs = 'transcribe the video first';
  if (has_transcript.value) {
    if (list.length <= 1) {
      subs = 'only the spoken language so far — add one to translate it';
    } else if (stale.length) {
      subs = `${list.length} languages — ${ready} ready, `
        + `${stale.map((item) => item.name).join(', ')} out of date`;
    } else {
      subs = `${list.length} languages, all ready`;
    }
  }

  let deliver = 'build a subtitle first';
  if (deliver_state.value === 'done') {
    deliver = `one video carrying ${delivery_tracks} subtitles, up to date`;
  } else if (deliver_state.value === 'stale') {
    deliver = 'the video was made before the last subtitle change';
  } else if (list.some((item) => item.paths?.subs)) {
    deliver = `one video with all ${list.length} subtitles, switchable in any player`;
  }

  return { source, subtitles: subs, deliver };
});

export const setStep = (id) => {
  step.value = id;
  step_chosen = true;
  persist();
};

/* Where the work actually is, used once on load so the page opens on the thing
   that needs doing — never against a choice the owner already made. */
export const suggested_step = computed(() => {
  if (source_state.value !== 'done') {
    return 'source';
  }
  if (subtitles_state.value !== 'done' || subtitles.value.length <= 1) {
    return 'subtitles';
  }
  return deliver_state.value === 'done' ? 'subtitles' : 'deliver';
});

export const next_hint = computed(() => {
  if (!has_input.value) {
    return 'open a video or audio file to start';
  }
  if (source_state.value !== 'done') {
    return 'step 1 — transcribe the video, every subtitle is built from that text';
  }
  const stale = needs_rebuild.value;
  if (stale.length) {
    return `step 2 — ${stale.map((item) => item.name).join(' and ')} out of date, rebuild `
      + `${stale.length > 1 ? 'them' : 'it'}`;
  }
  if (subtitles.value.length <= 1) {
    return 'step 2 — add a language, or build the subtitle for the spoken one';
  }
  if (deliver_state.value !== 'done') {
    return 'step 3 — put the subtitles into a video';
  }
  return 'everything is up to date';
});

export default {
  connect,
  start,
  refreshState,
  refreshStyles,
  refreshPreview,
  schedulePreview,
};
