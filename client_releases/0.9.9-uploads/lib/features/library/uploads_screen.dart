import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/uploads/upload_queue.dart';

class UploadsScreen extends ConsumerWidget {
  const UploadsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final uploads = ref.watch(uploadQueueProvider);
    final queue = ref.read(uploadQueueProvider.notifier);
    final completed = uploads.where((j) => j.status == UploadStatus.completed).length;
    return Scaffold(
      appBar: AppBar(title: const Text('Uploads'),
        leading: IconButton(icon: const Icon(Icons.arrow_back), onPressed: () => context.go('/chat')),
        actions: [TextButton(onPressed: queue.clearFinished, child: const Text('Clear finished'))]),
      body: Center(child: ConstrainedBox(constraints: const BoxConstraints(maxWidth: 820), child: ListView(
        padding: const EdgeInsets.all(16), children: [
          Text('$completed of ${uploads.length} saved to library', style: Theme.of(context).textTheme.titleMedium),
          const Text('You can change chats or pages while these uploads continue. Keep the app open: closing, refreshing, signing out or changing servers stops pending work. An upload already received by the server may still finish.'),
          TextButton(onPressed: () => context.go('/library'), child: const Text('Open Knowledge library')),
          if (uploads.isEmpty) const Text('No uploads in this session.'),
          for (final job in uploads) Card(child: Padding(padding: const EdgeInsets.all(12), child: Column(
            crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(job.name, style: Theme.of(context).textTheme.titleSmall),
              Text(job.label),
              if (job.busy) const LinearProgressIndicator(),
              if (job.projectId != null) Text('Destination project: ${job.projectId}'),
              if (job.document?.notes != null) Text(job.document!.notes!),
              if (job.error != null) SelectableText(job.error!),
              if (job.status == UploadStatus.failed) const Text('Check the library before retrying: the server may have saved the original upload. Nothing is retried automatically.'),
              Wrap(spacing: 8, children: [
                if (const [UploadStatus.queued, UploadStatus.preparing].contains(job.status)) TextButton(
                  onPressed: () => queue.cancel(job.id), child: const Text('Cancel queued upload')),
                if (job.status == UploadStatus.failed) TextButton(onPressed: () async {
                  final confirmed = await showDialog<bool>(context: context, builder: (context) => AlertDialog(
                    title: const Text('Retry this upload?'),
                    content: const Text('If the server already saved it, retrying can create a duplicate. Check your library first.'),
                    actions: [TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
                      FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Retry upload'))],
                  ));
                  if (confirmed == true && context.mounted) queue.retry(job.id);
                }, child: const Text('Retry upload')),
                if (job.target?.startsWith('conversation:') == true) TextButton(
                  onPressed: () => context.go('/chat/${job.target!.substring('conversation:'.length)}'), child: const Text('Open original chat')),
              ]),
            ],
          ))),
        ],
      ))),
    );
  }
}
