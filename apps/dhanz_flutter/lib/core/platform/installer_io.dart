import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:http/http.dart' as http;
import 'package:path_provider/path_provider.dart';

/// Downloads the Windows installer, checks its SHA-256 against the release manifest, then runs it
/// silently (Inno Setup closes the app, installs, and starts the new version) and exits.
Future<void> installWindowsUpdate(
  Uri url,
  String sha256Hex, {
  required http.Client client,
  void Function(double progress)? onProgress,
}) async {
  final file = await downloadVerified(url, sha256Hex, client: client, onProgress: onProgress);
  await Process.start(file.path, const ['/SILENT', '/CLOSEAPPLICATIONS'], mode: ProcessStartMode.detached);
  exit(0);
}

/// Downloads [url] to a temporary file and returns it only if its SHA-256 matches [sha256Hex].
Future<File> downloadVerified(
  Uri url,
  String sha256Hex, {
  required http.Client client,
  void Function(double progress)? onProgress,
  Directory? directory,
}) async {
  if (url.scheme != 'https') throw const HttpException('Updates are only downloaded over HTTPS.');
  final res = await client.send(http.Request('GET', url));
  if (res.statusCode != 200) throw HttpException('Download failed (${res.statusCode}).', uri: url);
  final dir = directory ?? await getTemporaryDirectory();
  final file = File('${dir.path}${Platform.pathSeparator}DhanzAI-update-setup.exe');
  final sink = file.openWrite();
  var received = 0;
  try {
    await for (final chunk in res.stream) {
      sink.add(chunk);
      received += chunk.length;
      final total = res.contentLength;
      if (total != null && total > 0) onProgress?.call(received / total);
    }
  } finally {
    await sink.close();
  }
  final digest = await sha256.bind(file.openRead()).first;
  if (digest.toString() != sha256Hex.toLowerCase()) {
    await file.delete();
    throw const FileSystemException('The downloaded update did not match its checksum and was deleted.');
  }
  return file;
}
