import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:flutter/services.dart';
import 'package:http/http.dart' as http;
import 'package:path_provider/path_provider.dart';

/// Downloads the Windows installer, checks its SHA-256 against the release manifest, then runs it
/// silently (Inno Setup closes the app, installs, and starts the new version) and exits.
Future<void> installWindowsUpdate(
  Uri url,
  String sha256Hex, {
  required http.Client client,
  void Function(double progress)? onProgress,
  String? downloadedPath,
}) async {
  final file = downloadedPath == null
      ? await downloadVerified(url, sha256Hex, client: client, onProgress: onProgress)
      : File(downloadedPath);
  if ((await sha256.bind(file.openRead()).first).toString() != sha256Hex.toLowerCase()) {
    throw const FileSystemException('The update checksum changed. Download it again.');
  }
  await Process.start(file.path, const ['/SILENT', '/CLOSEAPPLICATIONS'], mode: ProcessStartMode.detached);
  exit(0);
}

Future<String> prepareWindowsUpdate(
  Uri url,
  String checksum, {
  required http.Client client,
  void Function(double)? onProgress,
}) async => (await downloadVerified(url, checksum, client: client, onProgress: onProgress)).path;

Future<String> prepareAndroidUpdate(
  Uri url,
  String checksum, {
  required http.Client client,
  void Function(double)? onProgress,
}) async => (await downloadVerified(url, checksum, client: client, onProgress: onProgress, extension: 'apk')).path;

/// Returns false when Android needs the user to grant installation permission.
Future<bool> installAndroidUpdate(String path) async =>
    await const MethodChannel('ai.dhanz/updates').invokeMethod<bool>('installApk', {'path': path}) ?? false;

/// Downloads [url] to a temporary file and returns it only if its SHA-256 matches [sha256Hex].
Future<File> downloadVerified(
  Uri url,
  String sha256Hex, {
  required http.Client client,
  void Function(double progress)? onProgress,
  Directory? directory,
  String extension = 'exe',
}) async {
  if (!const {'exe', 'apk'}.contains(extension)) throw const FormatException('Unsupported update type');
  if (url.scheme != 'https') throw const HttpException('Updates are only downloaded over HTTPS.');
  if (!RegExp(r'^[a-fA-F0-9]{64}$').hasMatch(sha256Hex)) throw const FormatException('Invalid checksum');
  final dir = directory ?? await getTemporaryDirectory();
  final cache = Directory('${dir.path}${Platform.pathSeparator}dhanz-ai-updates');
  await cache.create(recursive: true);
  final file = File('${cache.path}${Platform.pathSeparator}$sha256Hex-setup.$extension');
  if (await file.exists() && (await sha256.bind(file.openRead()).first).toString() == sha256Hex.toLowerCase()) {
    return file;
  }
  final res = await client.send(http.Request('GET', url)).timeout(const Duration(seconds: 30));
  if (res.statusCode != 200) throw HttpException('Download failed (${res.statusCode}).', uri: url);
  final sink = file.openWrite();
  var received = 0;
  try {
    await for (final chunk in res.stream.timeout(const Duration(seconds: 60))) {
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
