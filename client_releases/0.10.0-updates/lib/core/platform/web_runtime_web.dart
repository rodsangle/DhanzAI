import 'dart:convert';
import 'dart:js_interop';

import 'package:web/web.dart' as web;

import 'web_runtime_types.dart';

WebUpdateRuntime createWebUpdateRuntime() => _BrowserUpdate();

class _BrowserUpdate implements WebUpdateRuntime {
  Uri get base => Uri.parse(web.document.baseURI);
  Future<web.Response> _fresh(String path) async {
    final url = base
        .resolve(path)
        .replace(
          queryParameters: {
            'dhanz_update': DateTime.now().microsecondsSinceEpoch.toString(),
          },
        );
    final response = await web.window
        .fetch(
          url.toString().toJS,
          web.RequestInit(cache: 'reload', credentials: 'same-origin'),
        )
        .toDart;
    if (!response.ok)
      throw StateError(
        'The server could not serve the updated app files (${response.status}).',
      );
    return response;
  }

  @override
  Future<WebBuild> servedBuild() async {
    final response = await _fresh('version.json');
    final data = jsonDecode(
      (await response.text().toDart).toDart,
    ) as Map<String, dynamic>;
    final result = (
      version: data['version'] as String,
      build: int.parse('${data['build_number']}'),
    );
    compareWebBuilds(result, result);
    return result;
  }

  @override
  Future<void> refresh(WebBuild minimum) async {
    if (compareWebBuilds(await servedBuild(), minimum) < 0) {
      throw StateError(
        'The server is still serving an older build. Its owner must install the GitHub update first.',
      );
    }
    final registrations =
        (await web.window.navigator.serviceWorker.getRegistrations().toDart)
            .toDart;
    for (final registration in registrations) {
      final scope = Uri.parse(registration.scope);
      final script =
          registration.active?.scriptURL ??
          registration.waiting?.scriptURL ??
          registration.installing?.scriptURL;
      if (scope.origin == base.origin &&
          {base.path, '/'}.contains(scope.path) &&
          script != null &&
          Uri.parse(script).path.endsWith('/flutter_service_worker.js')) {
        await registration.unregister().toDart;
      }
    }
    // Clear only Flutter response caches for this app. Tokens, uploads and other
    // localStorage/IndexedDB data are deliberately not erased.
    final names = (await web.window.caches.keys().toDart).toDart;
    for (final item in names) {
      final name = item.toDart;
      if (!name.startsWith('flutter-')) continue;
      final cache = await web.window.caches.open(name).toDart;
      final requests = (await cache.keys().toDart).toDart;
      for (final request in requests) {
        final uri = Uri.parse(request.url);
        if (uri.origin == base.origin &&
            (uri.path.startsWith(base.path) ||
                const ['/', '/index.html'].contains(uri.path))) {
          await cache.delete(request).toDart;
        }
      }
    }
    for (final file in [
      'version.json',
      'release.json',
      'flutter_bootstrap.js',
      'main.dart.js',
      'flutter.js',
    ]) {
      await _fresh(file);
    }
    final current = Uri.parse(web.window.location.href);
    web.window.location.replace(
      current
          .replace(
            queryParameters: {
              ...current.queryParameters,
              'dhanz_update':
                  '${minimum.version}-${minimum.build}-${DateTime.now().millisecondsSinceEpoch}',
            },
          )
          .toString(),
    );
  }
}
