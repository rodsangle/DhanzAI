import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../features/projects/projects_controller.dart';
import '../folder_picker.dart';
import 'upload_queue.dart';

/// Only choosing/reviewing belongs to the page. Preparation and upload belong to the queue.
Future<void> queueFolderUpload(
  BuildContext context,
  WidgetRef ref, {
  String? target,
}) async {
  final queue = ref.read(uploadQueueProvider.notifier);
  final ticket = queue.ticket();
  final project = ref.read(selectedProjectProvider);
  try {
    final picked = await pickFolder();
    if (picked.isEmpty || !context.mounted || !queue.accepts(ticket)) return;
    final files = checkedFolderFiles(picked);
    final skipped = picked.length - files.length;
    await showDialog<void>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Upload folder'),
        content: SizedBox(
          width: 520,
          child: SingleChildScrollView(
            child: Text(
              '${files.length} files will upload with their folder paths. $skipped private/build files excluded. Review for other secrets before uploading.\n\n'
              'After confirming you can switch chats or open the library. Keep this app open until uploads finish.\n\n'
              'Images and unsupported files stay in the archive and need separate uploads for analysis. Large folders may exceed a reply’s context window.\n\n'
              '${files.map((f) => f.path).join('\n')}',
            ),
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () {
              try {
                queue.folder(
                files,
                ticket: ticket,
                projectId: project,
                target: target,
              );
              Navigator.pop(context);
              } catch (error) {
                ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('$error')));
              }
            },
            child: const Text('Upload folder'),
          ),
        ],
      ),
    );
  } catch (error) {
    if (context.mounted) {
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text('$error')));
    }
  }
}
