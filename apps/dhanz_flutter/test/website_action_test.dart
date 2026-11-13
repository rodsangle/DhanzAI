import 'package:dhanz_ai/features/chat/website_action.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('website actions accept HTTPS and reject unsafe schemes and credentials', () {
    expect(websiteUri('https://www.sortly.com/'), isNotNull);
    for (final value in [
      'javascript:alert(1)',
      'http://sortly.com',
      'https://user:password@sortly.com',
      'https://sortly.com:8443',
    ]) {
      expect(websiteUri(value), isNull);
    }
  });
}
