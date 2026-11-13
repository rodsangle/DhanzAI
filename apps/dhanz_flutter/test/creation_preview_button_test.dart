import 'package:dhanz_ai/features/chat/chat_preview.dart';
import 'package:dhanz_ai/features/chat/media_generation_card.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  const job = {'id': 'job-1', 'kind': 'video', 'prompt': 'Waves rolling onto a beach at dusk', 'has_media': true};

  testWidgets('a finished photo or video opens in the chat side panel like a file preview', (tester) async {
    final controller = ChatPreviewController();
    await tester.pumpWidget(
      MaterialApp(
        home: ChatPreviewScope(
          controller: controller,
          child: Builder(
            builder: (context) => TextButton(
              onPressed: () => openCreationPreview(context, Map<String, dynamic>.from(job)),
              child: const Text('Preview'),
            ),
          ),
        ),
      ),
    );
    await tester.tap(find.text('Preview'));
    await tester.pump();
    expect(controller.visible, isTrue);
    expect(controller.target!.creation!['id'], 'job-1');
    expect(controller.target!.documentId, 'creation:job-1');
    expect(controller.target!.filename, 'Video · Waves rolling onto a beach at dusk');
  });
}
