/*
 * Copyright (c) 2026 Cristian D. Moreno — @Kyonax
 * Distributed under the terms of MIT — see LICENSE.
 *
 * The page mounts one view. No router and no i18n: this is a local control
 * room for one tool, not a site.
 */

import '@scss/main.scss';

import { createApp } from 'vue';

import App from './App.vue';

createApp(App).mount('#root');
