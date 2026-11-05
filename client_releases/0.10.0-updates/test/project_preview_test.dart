import 'package:flutter_test/flutter_test.dart';
import 'package:dhanz_ai/features/builder/preview_document.dart';

void main() {
  test('preview inlines project assets and blocks network/forms/host access', () {
    final html = previewDocument([
      {'path': 'index.html', 'content': '<link href="style.css" rel="stylesheet"><script src="app.js"></script>'},
      {'path': 'style.css', 'content': 'body { color: red; }'},
      {'path': 'app.js', 'content': 'document.title = "Preview";'},
    ]);
    expect(html, contains('body { color: red; }'));
    expect(html, contains('document.title = "Preview";'));
    expect(html, contains("connect-src 'none'"));
    expect(html, contains("form-action 'none'"));
    expect(html, contains("frame-src 'none'"));
    expect(html.indexOf('Content-Security-Policy'), lessThan(html.indexOf('body {')));
  });
}
