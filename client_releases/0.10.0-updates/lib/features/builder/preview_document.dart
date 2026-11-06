/// Preview code runs in an opaque-origin iframe without network access.
String previewDocument(List<Map<String, dynamic>> files, {String entryPath = 'index.html'}) {
  final content = {for (final file in files) file['path'] as String: file['content'] as String};
  final directory = entryPath.contains('/') ? entryPath.substring(0, entryPath.lastIndexOf('/') + 1) : '';
  String? asset(String path) {
    final parts = <String>[];
    for (final part in ('$directory$path').split('/')) {
      if (part == '..') {
        if (parts.isEmpty) return null;
        parts.removeLast();
      } else if (part.isNotEmpty && part != '.') {
        parts.add(part);
      }
    }
    return content[parts.join('/')];
  }
  var html = content[entryPath] ?? '<p>No browser demo was generated.</p>';
  html = html.replaceAllMapped(
    RegExp(r'''<script\b[^>]*\bsrc=["']([^"']+)["'][^>]*>\s*</script>''', caseSensitive: false),
    (match) {
      final source = asset(match[1]!);
      return source == null ? match[0]! : '<script>${source.replaceAll('</script', r'<\/script')}</script>';
    },
  );
  html = html.replaceAllMapped(RegExp(r'''<link\b[^>]*\bhref=["']([^"']+\.css)["'][^>]*>''', caseSensitive: false), (
    match,
  ) {
    final source = asset(match[1]!);
    return source == null ? match[0]! : '<style>${source.replaceAll('</style', r'<\/style')}</style>';
  });
  const policy =
      "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data: blob:; "
      "font-src data:; connect-src 'none'; form-action 'none'; base-uri 'none'; frame-src 'none'; object-src 'none'";
  return '<!doctype html><html><head><meta http-equiv="Content-Security-Policy" content="$policy"></head><body>$html</body></html>';
}
