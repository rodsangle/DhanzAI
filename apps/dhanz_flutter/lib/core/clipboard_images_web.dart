import 'dart:js_interop';

import 'package:web/web.dart' as web;

import 'clipboard_images_types.dart';

ClipboardImageSource source(web.Blob blob, int index) {
  final ext = switch (blob.type) {
    'image/jpeg' => 'jpg',
    'image/webp' => 'webp',
    'image/gif' => 'gif',
    _ => 'png',
  };
  return ClipboardImageSource(
    name: 'Clipboard-${DateTime.now().millisecondsSinceEpoch}-$index.$ext',
    mime: blob.type,
    size: blob.size,
    read: () async => (await blob.arrayBuffer().toDart).toDart.asUint8List(),
  );
}

void Function() bindClipboardImages({
  required bool Function() active,
  required void Function(List<ClipboardImageSource>) onImages,
}) {
  final listener = ((web.Event raw) {
    if (!active() || !raw.isA<web.ClipboardEvent>()) {
      return;
    }
    final event = raw as web.ClipboardEvent;
    final items = event.clipboardData?.items;
    if (items == null) {
      return;
    }
    final images = <ClipboardImageSource>[];
    for (var index = 0; index < items.length; index++) {
      final item = items[index];
      if (item.kind == 'file' && clipboardImageTypes.contains(item.type)) {
        final file = item.getAsFile();
        if (file != null) {
          images.add(source(file, index));
        }
      }
    }
    if (images.isNotEmpty) {
      event.preventDefault();
      onImages(images);
    }
  }).toJS;
  web.document.addEventListener('paste', listener);
  return () => web.document.removeEventListener('paste', listener);
}

Future<List<ClipboardImageSource>> readClipboardImages() async {
  try {
    final items = (await web.window.navigator.clipboard.read().toDart).toDart;
    final images = <ClipboardImageSource>[];
    for (final item in items) {
      final types = item.types.toDart.map((value) => value.toDart);
      final mime = types.where(clipboardImageTypes.contains).firstOrNull;
      if (mime != null) {
        images.add(source(await item.getType(mime).toDart, images.length));
      }
    }
    return images;
  } catch (_) {
    throw StateError('Clipboard access was blocked. Click the chat input and press Ctrl+V, or use Attach files.');
  }
}
