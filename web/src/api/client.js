/*
 * Copyright (c) 2026 Cristian D. Moreno — @Kyonax
 * Distributed under the terms of MIT — see LICENSE.
 *
 * client.js — every call the page makes to the local Python server.
 *
 * One rule: the server owns the truth. Nothing here caches state, every action
 * ends with the page refetching /api/job, and errors carry the server's own
 * words (they are written for a person, not for a stack trace).
 */

const request = async (path, { method = 'GET', body, signal } = {}) => {
  const response = await fetch(path, {
    method,
    signal,
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const text = await response.text();
  const payload = text ? JSON.parse(text) : {};
  if (!response.ok) {
    const error = new Error(payload.error || `${response.status} ${response.statusText}`);
    error.status = response.status;
    error.busy = Boolean(payload.busy);
    throw error;
  }
  return payload;
};

const query = (params) => {
  const search = new URLSearchParams();
  Object.entries(params || {}).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      search.set(key, value);
    }
  });
  const rendered = search.toString();
  return rendered ? `?${rendered}` : '';
};

export const api = {
  health:  (input) => request(`/api/health${query({ input })}`),
  browse:  (path) => request(`/api/browse${query({ path })}`),
  job:     (input, track) => request(`/api/job${query({ input, track })}`),
  jobs:    () => request('/api/jobs'),

  run: (stage, input, options = {}) => request('/api/run', {
    method: 'POST',
    body: { stage, input, options },
  }),

  editSegment: (input, track, id, text) => request('/api/segment', {
    method: 'POST',
    body: { input, track, id, text },
  }),

  renameSpeaker: (input, speaker_id, name) => request('/api/speaker', {
    method: 'POST',
    body: { input, speaker_id, name },
  }),

  removeTrack: (input, track) => request('/api/track/remove', {
    method: 'POST',
    body: { input, track },
  }),

  styles:      (input, preset) => request(`/api/styles${query({ input, preset })}`),
  saveStyles:  (input, raw) => request('/api/styles', { method: 'PUT', body: { input, raw } }),
  setStyle:    (input, table, key, value) => request('/api/styles/set', {
    method: 'POST',
    body: { input, table, key, value },
  }),
  preset: (input, name, action) => request('/api/styles/preset', {
    method: 'POST',
    body: { input, name, action },
  }),

  /* The preview comes back as an image plus three headers that say what it is:
     which segment it belongs to, the exact second it was taken at, and whether
     it is a real frame or the sample-text card. */
  preview: async (params, signal) => {
    const response = await fetch(`/api/preview${query(params)}`, { signal });
    if (!response.ok) {
      const text = await response.text();
      let message = text;
      try {
        message = JSON.parse(text).error || text;
      } catch {
        /* the server answered with plain text */
      }
      throw new Error(message || 'preview failed');
    }
    return {
      blob: await response.blob(),
      at: Number.parseFloat(response.headers.get('X-Preview-At')) || null,
      segment: response.headers.get('X-Preview-Segment') || null,
      mode: response.headers.get('X-Preview-Mode') || 'sample',
    };
  },

  fileUrl: (path, extra = {}) => `/api/file${query({ path, ...extra })}`,

  /* Server-sent events: logs, stage progress, job starts and ends. The browser
     reconnects on its own; `after` replays what was missed. */
  events: (onEvent, onStatus) => {
    let source = null;
    let last_seq = 0;
    let closed = false;

    const connect = () => {
      if (closed) {
        return;
      }
      source = new EventSource(`/api/events${query({ after: last_seq || undefined })}`);
      source.onopen = () => onStatus?.('live');
      source.onmessage = (event) => {
        const payload = JSON.parse(event.data);
        last_seq = payload.seq || last_seq;
        onEvent(payload);
      };
      source.onerror = () => {
        onStatus?.('reconnecting');
        source.close();
        if (!closed) {
          setTimeout(connect, 1200);
        }
      };
    };

    connect();
    return () => {
      closed = true;
      source?.close();
    };
  },
};

export default api;
