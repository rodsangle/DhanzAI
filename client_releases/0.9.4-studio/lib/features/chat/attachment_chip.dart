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
    if (!context.mounted) return;
    if (await saveBytes(filename, bytes)) {
      if (context.mounted) messenger.showSnackBar(SnackBar(content: Text('Saved $filename')));
    } else if (context.mounted) {
      messenger.showSnackBar(const SnackBar(content: Text('Download cancelled. Choose a location to save the file.')));
    }
  } on ApiException catch (e) {
    if (context.mounted) messenger.showSnackBar(SnackBar(content: Text(e.message)));
  } catch (_) {
    if (context.mounted) {
      messenger.showSnackBar(const SnackBar(content: Text('Could not save the file. Please try Download again.')));
    }
  }
}

/// A file attached to a message; tap to download it.
class AttachmentChip extends ConsumerWidget {
  const AttachmentChip({
    super.key,
    required this.documentId,
    required this.filename,
    this.fileType,
    this.previewEnabled = false,
  });

  final String documentId;
  final String filename;
  final String? fileType;
  final bool previewEnabled;

  @override
  Widget build(BuildContext context, WidgetRef ref) => Wrap(
    spacing: 8,
    runSpacing: 8,
    children: [
      if (previewEnabled)
        ActionChip(
          avatar: const Icon(Icons.visibility_outlined, size: 18),
          label: const Text('Preview'),
          tooltip: 'Preview $filename',
          onPressed: () => showDialog<void>(
            context: context,
            builder: (_) => _FilePreview(documentId: documentId, filename: filename),
          ),
        ),
      Chip(
        avatar: Icon(fileIcon(fileType), size: 18),
        label: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 220),
          child: Text(filename, overflow: TextOverflow.ellipsis),
        ),
      ),
      DocumentDownloadButton(documentId: documentId, filename: filename),
    ],
  );
}

class DocumentDownloadButton extends ConsumerStatefulWidget {
  const DocumentDownloadButton({required this.documentId, required this.filename, super.key});
  final String documentId;
  final String filename;

  @override
  ConsumerState<DocumentDownloadButton> createState() => _DocumentDownloadButtonState();
}

class _DocumentDownloadButtonState extends ConsumerState<DocumentDownloadButton> {
  bool _downloading = false;

  Future<void> _download() async {
    setState(() => _downloading = true);
    try {
      await downloadAndSave(context, ref, widget.documentId, widget.filename);
    } finally {
      if (mounted) setState(() => _downloading = false);
    }
  }

  @override
  Widget build(BuildContext context) => FilledButton.icon(
    onPressed: _downloading || widget.documentId.startsWith('pending') ? null : _download,
    icon: _downloading
        ? const SizedBox.square(dimension: 18, child: CircularProgressIndicator(strokeWidth: 2))
        : const Icon(Icons.download),
    label: Text(_downloading ? 'Downloading…' : 'Download'),
  );
}

class _FilePreview extends ConsumerStatefulWidget {
  const _FilePreview({required this.documentId, required this.filename});
  final String documentId;
  final String filename;
  @override
  ConsumerState<_FilePreview> createState() => _FilePreviewState();
}

class _FilePreviewState extends ConsumerState<_FilePreview> {
  late Future<Map<String, dynamic>> _preview;
  int _section = 0;

  @override
  void initState() {
    super.initState();
    _preview = ref.read(apiClientProvider).previewFile(widget.documentId);
  }

  @override
  Widget build(BuildContext context) => Dialog(
    insetPadding: const EdgeInsets.all(16),
    child: SizedBox(
      width: 1000,
      height: MediaQuery.sizeOf(context).height * 0.85,
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(
                    widget.filename,
                    style: Theme.of(context).textTheme.titleLarge,
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
                IconButton(
                  tooltip: 'Close preview',
                  onPressed: () => Navigator.pop(context),
                  icon: const Icon(Icons.close),
                ),
              ],
            ),
            const Text('Content preview · Layout may differ in Office. Formulas are shown without recalculation.'),
            const Divider(),
            Expanded(
              child: FutureBuilder<Map<String, dynamic>>(
                future: _preview,
                builder: (context, snapshot) {
                  if (snapshot.connectionState != ConnectionState.done) {
                    return const Center(child: CircularProgressIndicator());
                  }
                  if (snapshot.hasError) {
                    final error = snapshot.error;
                    return Center(
                      child: Column(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Text(
                            error is ApiException
                                ? error.message
                                : 'Unable to load preview. You can still download this file.',
                          ),
                          TextButton(
                            onPressed: () => setState(() {
                              _preview = ref.read(apiClientProvider).previewFile(widget.documentId);
                            }),
                            child: const Text('Retry'),
                          ),
                        ],
                      ),
                    );
                  }
                  final data = snapshot.data!;
                  final sections = (data['sections'] as List<dynamic>? ?? []).cast<Map<String, dynamic>>();
                  if (sections.isEmpty) return const Center(child: Text('No preview content.'));
                  final selected = sections[_section.clamp(0, sections.length - 1)];
                  final rows = selected['rows'] as List<dynamic>?;
                  return Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      if (data['truncated'] == true)
                        const Padding(
                          padding: EdgeInsets.all(8),
                          child: Text('Preview shortened. Download the file to view all content.'),
                        ),
                      if (sections.length > 1)
                        SizedBox(
                          height: 48,
                          child: ListView(
                            scrollDirection: Axis.horizontal,
                            children: [
                              for (var i = 0; i < sections.length; i++)
                                Padding(
                                  padding: const EdgeInsets.only(right: 8),
                                  child: ChoiceChip(
                                    label: Text(sections[i]['title'] as String),
                                    selected: _section == i,
                                    onSelected: (_) => setState(() => _section = i),
                                  ),
                                ),
                            ],
                          ),
                        ),
                      Expanded(
                        child: SingleChildScrollView(
                          child: rows != null && rows.any((row) => (row as List).isNotEmpty)
                              ? SingleChildScrollView(
                                  scrollDirection: Axis.horizontal,
                                  child: Table(
                                    defaultColumnWidth: const FixedColumnWidth(180),
                                    border: TableBorder.all(color: Theme.of(context).dividerColor),
                                    children: [
                                      for (var i = 0; i < rows.length; i++)
                                        TableRow(
                                          decoration: i == 0
                                              ? BoxDecoration(
                                                  color: Theme.of(context).colorScheme.surfaceContainerHighest,
                                                )
                                              : null,
                                          children: [
                                            for (
                                              var j = 0;
                                              j <
                                                  rows.fold<int>(
                                                    0,
                                                    (n, row) => (row as List).length > n ? row.length : n,
                                                  );
                                              j++
                                            )
                                              Padding(
                                                padding: const EdgeInsets.all(8),
                                                child: SelectableText(
                                                  j < (rows[i] as List).length ? '${rows[i][j]}' : '',
                                                ),
                                              ),
                                          ],
                                        ),
                                    ],
                                  ),
                                )
                              : Padding(
                                  padding: const EdgeInsets.all(16),
                                  child: SelectableText(
                                    selected['text'] as String? ?? '',
                                    style: const TextStyle(fontSize: 16, height: 1.6),
                                  ),
                                ),
                        ),
                      ),
                    ],
                  );
                },
              ),
            ),
            const Divider(),
            Align(
              alignment: Alignment.centerRight,
              child: DocumentDownloadButton(documentId: widget.documentId, filename: widget.filename),
            ),
          ],
        ),
      ),
    ),
  );
}
