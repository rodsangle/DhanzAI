import 'web_runtime_types.dart';

WebUpdateRuntime createWebUpdateRuntime() => _Unavailable();

class _Unavailable implements WebUpdateRuntime {
  @override
  Future<WebBuild> servedBuild() async => throw UnsupportedError('Web refresh requires a browser.');
  @override
  Future<void> refresh(WebBuild minimum) async => throw UnsupportedError('Web refresh requires a browser.');
}
