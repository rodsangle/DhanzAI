import 'web_runtime_stub.dart'
    if (dart.library.js_interop) 'web_runtime_web.dart'
    as platform;
import 'web_runtime_types.dart';
export 'web_runtime_types.dart';

WebUpdateRuntime createWebUpdateRuntime() => platform.createWebUpdateRuntime();
