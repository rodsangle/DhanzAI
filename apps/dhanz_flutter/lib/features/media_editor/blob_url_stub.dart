import 'dart:typed_data';

String mediaObjectUrl(Uint8List bytes, String mime) => Uri.dataFromBytes(bytes, mimeType: mime).toString();
void revokeMediaObjectUrl(String url) {}
