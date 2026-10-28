import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api/api_client.dart';
import '../../core/files.dart';
import '../../core/providers.dart';
import 'file_icons.dart';

/// Downloads an uploaded file from the server and offers to save it.
Future<void> downloadAndSave(BuildContext context, WidgetRef ref, String documentId, String filename) async {
  final messenger = ScaffoldMessenger.of(context);
  try {
    final bytes = await ref.read(apiClientProvider).downloadFile(documentId);
    if (await saveBytes(filename, bytes)) {
      messenger.showSnackBar(SnackBar(content: Text('Saved $filename')));
    }
  } on ApiException catch (e) {
    messenger.showSnackBar(SnackBar(content: Text(e.message)));
  }
}

/// A file attached to a message; tap to download it.
class AttachmentChip extends ConsumerWidget {
  const AttachmentChip({super.key, required this.documentId, required this.filename, this.fileType});

  final String documentId;
  final String filename;
  final String? fileType;

  @override
  Widget build(BuildContext context, WidgetRef ref) => ActionChip(
    avatar: Icon(fileIcon(fileType), size: 18),
    label: ConstrainedBox(
      constraints: const BoxConstraints(maxWidth: 220),
      child: Text(filename, overflow: TextOverflow.ellipsis),
    ),
    tooltip: 'Download $filename',
    onPressed: documentId.startsWith('pending') ? null : () => downloadAndSave(context, ref, documentId, filename),
  );
}
