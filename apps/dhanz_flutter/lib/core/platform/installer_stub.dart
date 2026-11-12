import 'package:http/http.dart' as http;

Future<String> prepareAndroidUpdate(
  Uri url,
  String checksum, {
  required http.Client client,
  void Function(double)? onProgress,
}) => throw UnsupportedError('Android only');

Future<bool> installAndroidUpdate(String path) => throw UnsupportedError('Android only');

Future<void> installWindowsUpdate(
  Uri url,
  String sha256Hex, {
  required http.Client client,
  void Function(double progress)? onProgress,
  String? downloadedPath,
}) => throw UnsupportedError('Installing updates is only supported on Windows.');

Future<String> prepareWindowsUpdate(
  Uri url,
  String checksum, {
  required http.Client client,
  void Function(double)? onProgress,
}) => throw UnsupportedError('Windows only');
