import 'dart:convert';
import 'dart:js_interop';

import 'package:web/web.dart' as web;

import 'web_runtime_types.dart';

WebUpdateRuntime createWebUpdateRuntime() => _BrowserUpdate();

class _BrowserUpdate implements WebUpdateRuntime {
  Uri get base => Uri.parse(web.document.baseURI);
  Future<web.Response> _fresh(String path, {bool bust = true}) async {
    final plain = base.resolve(path);
    final url = bust
        ? plain.replace(queryParameters: {'dhanz_update': DateTime.now().microsecondsSinceEpoch.toString()})
        : plain;
    final response = await web.window
        .fetch(url.toString().toJS, web.RequestInit(cache: 'reload', credentials: 'same-origin'))
        .toDart;
    if (!response.ok) {
      throw StateError('The server could not serve the updated app files (${response.status}).');
    }
    return response;
  }

  @override
  Future<WebBuild> servedBuild() async {
    final response = await _fresh('version.json');
    final data = jsonDecode((await response.text().toDart).toDart) as Map<String, dynamic>;
    final result = (version: data['version'] as String, build: int.parse('${data['build_number']}'));
    compareWebBuilds(result, result);
    return result;
  }

  @override
  Future<void> refresh(WebBuild minimum) async {
    if (compareWebBuilds(await servedBuild(), minimum) < 0) {
      throw StateError('The server is still serving an older build. Its owner must install the GitHub update first.');
    }
    final current = Uri.parse(web.window.location.href);
    final target = base
        .resolve('update.html')
        .replace(
          queryParameters: {
            'auto': '1',
            'min_version': minimum.version,
            'min_build': '${minimum.build}',
            'return':
                '${current.path}${current.hasQuery ? '?${current.query}' : ''}${current.hasFragment ? '#${current.fragment}' : ''}',
            'dhanz_update': DateTime.now().microsecondsSinceEpoch.toString(),
          },
        );
    web.window.location.replace(target.toString());
  }
}
