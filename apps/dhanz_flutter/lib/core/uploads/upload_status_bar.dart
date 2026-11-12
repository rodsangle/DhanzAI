import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../router.dart';
import 'upload_queue.dart';

class UploadStatusBar extends ConsumerWidget {
  const UploadStatusBar({super.key, required this.child});
  final Widget child;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final jobs = ref.watch(uploadQueueProvider);
    final busy = jobs.where((j) => j.busy).length;
    final failed = jobs.where((j) => j.status == UploadStatus.failed).length;
    return Column(
      children: [
        if (jobs.isNotEmpty)
          Material(
            color: Theme.of(context).colorScheme.surfaceContainerHigh,
            child: SafeArea(
              bottom: false,
              child: Row(
                children: [
                  const SizedBox(width: 12),
                  if (busy > 0)
                    const SizedBox.square(dimension: 16, child: CircularProgressIndicator(strokeWidth: 2))
                  else
                    Icon(failed > 0 ? Icons.error_outline : Icons.check_circle_outline, size: 18),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      busy > 0
                          ? '$busy upload${busy == 1 ? '' : 's'} continue in background'
                          : failed > 0
                          ? '$failed upload${failed == 1 ? '' : 's'} need attention'
                          : 'Uploads saved to library',
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                  TextButton(onPressed: () => ref.read(routerProvider).go('/uploads'), child: const Text('Uploads')),
                ],
              ),
            ),
          ),
        Expanded(child: child),
      ],
    );
  }
}
