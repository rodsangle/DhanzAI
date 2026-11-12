import 'dart:typed_data';

class ClipboardImageSource {
  const ClipboardImageSource({required this.name, required this.mime, required this.size, required this.read});
  final String name;
  final String mime;
  final int size;
  final Future<Uint8List> Function() read;
}

const clipboardImageTypes = {'image/png', 'image/jpeg', 'image/webp', 'image/gif'};

void validateClipboardImages(List<ClipboardImageSource> images) {
  if (images.isEmpty) {
    throw StateError('No image was found. Copy a screenshot or image, then paste again.');
  }
  if (images.length > 4 || images.fold<int>(0, (sum, image) => sum + image.size) > 20 * 1024 * 1024) {
    throw StateError('Paste at most four images and 20 MB at once.');
  }
  for (final image in images) {
    if (!clipboardImageTypes.contains(image.mime) || image.size < 1 || image.size > 10 * 1024 * 1024) {
      throw StateError('Use PNG, JPEG, WebP or GIF images up to 10 MB each.');
    }
  }
}
