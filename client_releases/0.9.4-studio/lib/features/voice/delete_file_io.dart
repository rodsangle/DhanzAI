import 'dart:io';

/// Removes a temporary recording from the device.
Future<void> deleteTempFile(String path) async {
  final file = File(path);
  if (await file.exists()) await file.delete();
}
