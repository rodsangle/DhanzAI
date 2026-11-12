const {test} = require('node:test');
const assert = require('node:assert/strict');
const {refreshInstalledApp, compare} = require('../client_releases/0.10.0-updates/web/force_update.js');

function browser(version = '0.10.0', build = 28) {
  const fetched = [], removed = [], unregistered = [], navigated = [], consumed = [];
  const origin = 'https://dhanzai.com';
  const registration = (scope, script) => ({scope: origin + scope, active: {scriptURL: origin + script},
    async unregister() { unregistered.push(scope); }});
  const env = {
    location: {href: origin + '/app/update.html', replace(url) {
      assert.equal(consumed.length, 5, 'all loader bodies must finish before reload'); navigated.push(url);
    }},
    navigator: {serviceWorker: {async getRegistrations() { return [
      registration('/app/', '/app/flutter_service_worker.js'),
      registration('/', '/firebase-messaging-sw.js'),
      registration('/other/', '/other/flutter_service_worker.js'),
    ]; }}},
    caches: {
      async keys() { return ['flutter-app-cache', 'private-user-data']; },
      async open(name) {
        assert.equal(name, 'flutter-app-cache');
        return {
          async keys() { return ['/app/main.dart.js', '/index.html', '/api/v1/private', '/other/data'].map(path => ({url: origin + path})); },
          async delete(request) { removed.push(request.url); },
        };
      },
    },
    async fetch(url, options) {
      fetched.push({url, options});
      assert.equal(new URL(url).origin, origin);
      return {ok: true, status: 200, async arrayBuffer() { consumed.push(url); return new ArrayBuffer(0); }, async json() { return {version, build_number: String(build)}; }};
    },
  };
  for (const name of ['localStorage', 'sessionStorage', 'indexedDB']) {
    Object.defineProperty(env, name, {get() { throw new Error('Account storage must not be touched'); }});
  }
  return {env, fetched, removed, unregistered, navigated, consumed};
}

test('force refresh clears only own Flutter responses and reloads actual loader cache entries', async () => {
  const b = browser();
  await refreshInstalledApp(b.env, {minimum: {version: '0.10.0', build: 28}, returnTo: '/app/#/settings'});
  assert.deepEqual(b.unregistered, ['/app/']); // Firebase and another app survive.
  assert.deepEqual(b.removed, ['https://dhanzai.com/app/main.dart.js', 'https://dhanzai.com/index.html']);
  const loader = b.fetched.find(item => item.url === 'https://dhanzai.com/app/main.dart.js');
  assert.ok(loader);
  assert.equal(loader.options.cache, 'reload');
  assert.equal(loader.options.credentials, 'same-origin');
  assert.equal(b.navigated.length, 1);
  assert.equal(new URL(b.navigated[0]).hash, '#/settings');
  assert.ok(new URL(b.navigated[0]).searchParams.has('dhanz_update'));
});

test('an older served build cannot be reported as the requested update', async () => {
  const b = browser('0.9.9', 27);
  await assert.rejects(refreshInstalledApp(b.env, {minimum: {version: '0.10.0', build: 28}}), /older build/);
  assert.deepEqual(b.navigated, []);
  assert.deepEqual(b.removed, []);
});

test('return URL cannot redirect outside this app or send credentials cross-origin', async () => {
  const b = browser();
  await assert.rejects(refreshInstalledApp(b.env, {returnTo: 'https://evil.example/'}), /inside this Dhanz app/);
  await assert.rejects(refreshInstalledApp(b.env, {returnTo: '/other/'}), /inside this Dhanz app/);
  assert.deepEqual(b.fetched, []);
});

test('version order compares numeric parts and the build counter', () => {
  assert.equal(compare({version: '0.10.0', build: 28}, {version: '0.9.9', build: 100}), 1);
  assert.equal(compare({version: '0.10.0', build: 29}, {version: '0.10.0', build: 28}), 1);
});
