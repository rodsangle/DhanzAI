/* Refresh only Dhanz Flutter caches. Never erase account or library storage. */
(function () {
  'use strict';
  function parts(version, build) {
    if (!/^\d+\.\d+\.\d+$/.test(version) || !Number.isInteger(build) || build < 0) {
      throw new Error('Invalid app version.');
    }
    return version.split('.').map(Number).concat(build);
  }
  function compare(a, b) {
    const x = parts(a.version, a.build), y = parts(b.version, b.build);
    for (let i = 0; i < x.length; i++) if (x[i] !== y[i]) return x[i] > y[i] ? 1 : -1;
    return 0;
  }
  async function refreshInstalledApp(env, options = {}) {
    const base = new URL('./', env.location.href);
    const destination = new URL(options.returnTo || './#/settings', base);
    if (destination.origin !== base.origin || !destination.pathname.startsWith(base.pathname)) {
      throw new Error('The return address must stay inside this Dhanz app.');
    }
    async function fresh(path, bust = false) {
      const url = new URL(path, base);
      if (bust) url.searchParams.set('dhanz_update', String(Date.now()));
      const response = await env.fetch(url.href, {cache: 'reload', credentials: 'same-origin'});
      if (!response.ok) throw new Error('Could not load app files (' + response.status + '). Please retry.');
      return response;
    }
    async function served() {
      const data = await (await fresh('version.json', true)).json();
      const value = {version: data.version, build: Number(data.build_number)};
      parts(value.version, value.build);
      return value;
    }
    const minimum = options.minimum || await served();
    if (compare(await served(), minimum) < 0) {
      throw new Error('Your server still serves an older build. Ask its owner to install the GitHub update first.');
    }
    if (env.navigator.serviceWorker) {
      const registrations = await env.navigator.serviceWorker.getRegistrations();
      for (const registration of registrations) {
        const scope = new URL(registration.scope);
        const worker = registration.active || registration.waiting || registration.installing;
        if (scope.origin === base.origin && [base.pathname, '/'].includes(scope.pathname) && worker &&
            new URL(worker.scriptURL).pathname.endsWith('/flutter_service_worker.js')) {
          await registration.unregister();
        }
      }
    }
    if (env.caches) {
      for (const name of await env.caches.keys()) {
        if (!name.startsWith('flutter-')) continue;
        const cache = await env.caches.open(name);
        for (const request of await cache.keys()) {
          const uri = new URL(request.url);
          if (uri.origin === base.origin && (uri.pathname.startsWith(base.pathname) || ['/', '/index.html'].includes(uri.pathname))) {
            await cache.delete(request);
          }
        }
      }
    }
    // Reload the actual loader URLs, not query-only copies: this replaces stale
    // entries in both HTTP cache and an old worker still controlling this page.
    for (const name of ['version.json', 'release.json', 'flutter_bootstrap.js', 'main.dart.js', 'flutter.js']) {
      const response = await fresh(name);
      await response.arrayBuffer(); // finish the download/cache write before navigating
    }
    if (compare(await served(), minimum) < 0) throw new Error('The server build changed during refresh. Please retry.');
    destination.searchParams.set('dhanz_update', minimum.version + '-' + minimum.build + '-' + Date.now());
    env.location.replace(destination.href);
  }
  if (typeof module !== 'undefined' && module.exports) module.exports = {refreshInstalledApp, compare};
  if (typeof document !== 'undefined') {
    const button = document.getElementById('refresh'), status = document.getElementById('status');
    async function start() {
      if (button.disabled) return;
      button.disabled = true;
      status.textContent = 'Loading current app files…';
      const params = new URL(window.location.href).searchParams;
      try {
        const minimum = params.has('min_version') ? {version: params.get('min_version'), build: Number(params.get('min_build'))} : null;
        await refreshInstalledApp(window, {minimum, returnTo: params.get('return')});
      } catch (error) {
        status.textContent = error.message || 'Refresh failed. Please retry.';
        button.disabled = false;
      }
    }
    button.addEventListener('click', start);
    if (new URL(window.location.href).searchParams.get('auto') === '1') start();
  }
})();
