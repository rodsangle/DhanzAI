import 'dart:typed_data';

import 'package:file_picker/file_picker.dart';

/// A file the user picked, read into memory.
typedef PickedFile = ({String name, Uint8List bytes});

/// Opens the platform file picker (multi-select) and reads the chosen files.
Future<List<PickedFile>> pickFiles() async {
  final picked = await FilePicker.pickFiles(dialogTitle: 'Attach files');
  return [for (final f in picked) (name: f.name, bytes: await f.readAsBytes())];
}

/// Saves bytes through the platform "save as" dialog (or share sheet on mobile).
/// Returns false if the user cancelled.
Future<bool> saveBytes(String fileName, Uint8List bytes, {String mimeType = 'application/octet-stream'}) async {
  final uri = await FilePicker.saveFile(
    fileName: fileName,
    bytes: bytes,
    mimeType: mimeType,
    dialogTitle: 'Save $fileName',
  );
  return uri != null;
}
