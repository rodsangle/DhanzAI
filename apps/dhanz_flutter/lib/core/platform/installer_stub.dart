import 'package:http/http.dart' as http;

Future<void> installWindowsUpdate(
  Uri url,
  String sha256Hex, {
  required http.Client client,
  void Function(double progress)? onProgress,
}) => throw UnsupportedError('Installing updates is only supported on Windows.');
