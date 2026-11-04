/// Preview code runs in an opaque-origin iframe without network access.
String previewDocument(List<Map<String, dynamic>> files) {
  final content = {for (final file in files) file['path'] as String: file['content'] as String};
  var html = content['index.html'] ?? '<p>No index.html was generated.</p>';
  html = html.replaceAllMapped(
    RegExp(r'''<script\b[^>]*\bsrc=["']([^"']+)["'][^>]*>\s*</script>''', caseSensitive: false),
    (match) {
      final source = content[match[1]!.replaceFirst(RegExp(r'^\./'), '')];
      return source == null ? match[0]! : '<script>${source.replaceAll('</script', r'<\/script')}</script>';
    },
  );
  html = html.replaceAllMapped(RegExp(r'''<link\b[^>]*\bhref=["']([^"']+\.css)["'][^>]*>''', caseSensitive: false), (
    match,
  ) {
    final source = content[match[1]!.replaceFirst(RegExp(r'^\./'), '')];
    return source == null ? match[0]! : '<style>${source.replaceAll('</style', r'<\/style')}</style>';
  });
  const policy =
      "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data: blob:; "
      "font-src data:; connect-src 'none'; form-action 'none'; base-uri 'none'; frame-src 'none'; object-src 'none'";
  return '<!doctype html><html><head><meta http-equiv="Content-Security-Policy" content="$policy"></head><body>$html</body></html>';
}
