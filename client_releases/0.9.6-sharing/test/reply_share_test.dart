import 'dart:async';

import 'package:dhanz_ai/features/chat/reply_share_button.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:share_plus/share_plus.dart';

void main() {
  testWidgets('shares only the selected text and prevents duplicate native sheets', (tester) async {
    final pending = Completer<ShareResult>();
    final requests = <ShareParams>[];
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: ReplyShareButton(
            text: 'Selected reply',
            share: (params) {
              requests.add(params);
              return pending.future;
            },
          ),
        ),
      ),
    );
    await tester.tap(find.byTooltip('Share reply'));
    await tester.pump();
    await tester.tap(find.byTooltip('Share reply'));
    expect(requests, hasLength(1));
    expect(requests.single.text, 'Selected reply');
    expect(requests.single.uri, isNull);
    expect(requests.single.files, isNull);
    expect(requests.single.mailToFallbackEnabled, isFalse);
    expect(requests.single.downloadFallbackEnabled, isFalse);
    expect(requests.single.sharePositionOrigin, isNotNull);
    pending.complete(const ShareResult('', ShareResultStatus.dismissed));
    await tester.pumpAndSettle();
    expect(find.text('Copy reply'), findsNothing);
    await tester.pumpWidget(const SizedBox.shrink());
  });

  testWidgets('unsupported sharing offers explicit copying and copies the actual reply', (tester) async {
    var clipboard = 'Keep until requested';
    tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(SystemChannels.platform, (call) async {
      if (call.method == 'Clipboard.setData') {
        clipboard = (call.arguments as Map<dynamic, dynamic>)['text'] as String;
      }
      return null;
    });
    addTearDown(() => tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(SystemChannels.platform, null));
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: ReplyShareButton(
            text: 'Reply to share',
            share: (_) async {
              throw UnsupportedError('Sharing not supported');
            },
          ),
        ),
      ),
    );
    await tester.tap(find.byTooltip('Share reply'));
    await tester.pumpAndSettle();
    expect(find.text('Copy reply'), findsOneWidget);
    expect(clipboard, 'Keep until requested');
    await tester.tap(find.text('Copy reply'));
    await tester.pumpAndSettle();
    expect(clipboard, 'Reply to share');
    expect(find.text('Reply copied'), findsOneWidget);
    await tester.pumpWidget(const SizedBox.shrink());
  });
}
