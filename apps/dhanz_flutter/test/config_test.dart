import 'package:dhanz_ai/core/config.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  tearDown(() => debugDefaultTargetPlatformOverride = null);

  test('default backend follows the browser origin or native development host', () {
    const override = String.fromEnvironment('DHANZ_API_URL');
    debugDefaultTargetPlatformOverride = TargetPlatform.android;
    expect(
      AppConfig.defaultApiUrl,
      override.isNotEmpty ? override : (kIsWeb ? Uri.base.origin : 'http://10.0.2.2:8000'),
    );
    debugDefaultTargetPlatformOverride = TargetPlatform.windows;
    expect(
      AppConfig.defaultApiUrl,
      override.isNotEmpty ? override : (kIsWeb ? Uri.base.origin : 'http://localhost:8000'),
    );
  });
}
