@TestOn('browser')
library;

import 'dart:js_interop';
import 'dart:typed_data';

import 'package:dhanz_ai/core/clipboard_images_web.dart';
import 'package:dhanz_ai/core/clipboard_images_types.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:web/web.dart' as web;

void main() {
  test('image paste is captured only while the chat input is active', () async {
    var active = false;
    final received = <ClipboardImageSource>[];
    final dispose = bindClipboardImages(active: () => active, onImages: received.addAll);
    final transfer = web.DataTransfer();
    final file = web.File(
      <JSAny>[
        Uint8List.fromList([1, 2, 3]).toJS,
      ].toJS,
      'clip.png',
      web.FilePropertyBag(type: 'image/png'),
    );
    transfer.items.add(file);
    web.ClipboardEvent event() =>
        web.ClipboardEvent('paste', web.ClipboardEventInit(clipboardData: transfer, cancelable: true));
    final ignored = event();
    web.document.dispatchEvent(ignored);
    expect(received, isEmpty);
    expect(ignored.defaultPrevented, false);
    active = true;
    final pasted = event();
    web.document.dispatchEvent(pasted);
    expect(received.length, 1);
    expect(pasted.defaultPrevented, true);
    expect(await received.single.read(), [1, 2, 3]);
    dispose();
    web.document.dispatchEvent(event());
    expect(received.length, 1);
  });

  test('plain text paste is not intercepted', () {
    var called = false;
    final dispose = bindClipboardImages(active: () => true, onImages: (_) => called = true);
    final transfer = web.DataTransfer();
    transfer.setData('text/plain', 'Normal text');
    final event = web.ClipboardEvent('paste', web.ClipboardEventInit(clipboardData: transfer, cancelable: true));
    web.document.dispatchEvent(event);
    expect(event.defaultPrevented, false);
    expect(called, false);
    dispose();
  });
}
