@TestOn('browser')
library;

import 'dart:async';
import 'dart:convert';
import 'dart:js_interop';
import 'package:flutter_test/flutter_test.dart';
import 'package:web/web.dart' as web;
import 'package:dhanz_ai/features/builder/preview_document.dart';

void main() {
  test('browser demo runs button logic without access to the Dhanz document', () async {
    final done = Completer<Map<String,dynamic>>();
    final listener = ((web.Event event) {
      final message = event as web.MessageEvent;
      final value = message.data;
      if (value != null && value.isA<JSString>()) {
        final data = (value as JSString).toDart;
        if (data.startsWith('{"dhanzSimulatorTest"')) {
          done.complete(jsonDecode(data) as Map<String,dynamic>);
        }
      }
    }).toJS;
    web.window.addEventListener('message', listener);
    final frame = web.HTMLIFrameElement();
    frame.setAttribute('sandbox', 'allow-scripts');
    frame.setAttribute('referrerpolicy', 'no-referrer');
    frame.setAttribute('srcdoc', previewDocument([
      {'path': 'simulator/index.html', 'content': '''<button id="lock">Lock demo</button><script>
        let locked=false;
        document.getElementById('lock').onclick=()=>{
          locked=!locked;
          let isolated=false;
          try { parent.document.body; } catch (_) { isolated=true; }
          parent.postMessage(JSON.stringify({dhanzSimulatorTest:true,locked,isolated}),'*');
        };
        document.getElementById('lock').click();
      </script>'''},
    ], entryPath: 'simulator/index.html'));
    web.document.body!.appendChild(frame);
    try {
      final result = await done.future.timeout(const Duration(seconds: 15));
      expect(result['locked'], true);
      expect(result['isolated'], true);
    } finally {
      frame.remove();
      web.window.removeEventListener('message', listener);
    }
  });
}
