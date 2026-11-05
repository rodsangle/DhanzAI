import 'clipboard_images_types.dart';

void Function() bindClipboardImages({
  required bool Function() active,
  required void Function(List<ClipboardImageSource>) onImages,
}) => () {};
Future<List<ClipboardImageSource>>
readClipboardImages() async => throw UnsupportedError(
  'Use Attach files on this device. Image pasting is available in the browser.',
);
