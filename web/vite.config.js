/*
 * Copyright (c) 2026 Cristian D. Moreno — @Kyonax
 * Distributed under the terms of MIT — see LICENSE.
 */

/*
 * vite.config.js — dev server, aliases, SCSS injection, build output.
 *
 * The page is a single local app served two ways:
 *   npm run dev    Vite on :5173, /api proxied to the Python server on :8765
 *   npm run build  dist/ served by `subtitle-studio web` itself
 *
 * Guidelines:
 *   Every kind-folder has an alias here, no relative parent imports in src/
 *   SCSS additionalData injects declarations ONLY (abstracts emits no CSS)
 *   The proxy must not buffer: /api/events is a server-sent-event stream
 */

import { fileURLToPath, URL } from 'node:url';

import vue from '@vitejs/plugin-vue';
import { defineConfig } from 'vite';

const r = (path) => fileURLToPath(new URL(path, import.meta.url));
const API_TARGET = process.env.STUDIO_API || 'http://127.0.0.1:8765';

export default defineConfig({
  plugins: [vue()],

  resolve: {
    alias: {
      '@api':         r('./src/api'),
      '@components':  r('./src/components'),
      '@composables': r('./src/composables'),
      '@panels':      r('./src/components/panels'),
      '@scss':        r('./src/scss'),
      '@ui':          r('./src/components/ui'),
      '@views':       r('./src/views'),
    },
  },

  css: {
    preprocessorOptions: {
      scss: {
        loadPaths: [r('./src/scss')],
        additionalData: '@use "abstracts" as *;\n',
        api: 'modern-compiler',
      },
    },
  },

  server: {
    port: 5173,
    strictPort: false,
    proxy: {
      '/api': {
        target: API_TARGET,
        changeOrigin: true,
        // server-sent events must stream through untouched
        configure: (proxy) => {
          proxy.on('proxyRes', (res) => {
            res.headers['cache-control'] = 'no-store';
          });
        },
      },
    },
  },

  build: {
    outDir: 'dist',
    emptyOutDir: true,
    target: 'es2020',
    sourcemap: false,
  },
});
