import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api/api_client.dart';
import '../../core/providers.dart';
import '../../models/models.dart';
import '../chat/file_icons.dart';

/// Office formats the server can preview without the user saving a copy first.
const previewableFileTypes = {'docx', 'xlsx', 'csv', 'pptx', 'pdf'};

Future<void> showFilePreview(
  BuildContext context,
  WidgetRef ref, {
  required String documentId,
  required String filename,
}) {
  return showDialog<void>(
    context: context,
    builder: (context) => FilePreviewDialog(documentId: documentId, filename: filename),
  );
}

class FilePreviewDialog extends ConsumerStatefulWidget {
  const FilePreviewDialog({required this.documentId, required this.filename, super.key});

  final String documentId;
  final String filename;

  @override
  ConsumerState<FilePreviewDialog> createState() => _FilePreviewDialogState();
}

class _FilePreviewDialogState extends ConsumerState<FilePreviewDialog> {
  FilePreview? _preview;
  Object? _error;
  final Map<int, Uint8List> _pages = {};

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final preview = await ref.read(apiClientProvider).filePreview(widget.documentId);
      if (!mounted) return;
      setState(() => _preview = preview);
      if (preview.kind == 'pdf') {
        for (var page = 1; page <= preview.pageCount; page++) {
          final bytes = await ref.read(apiClientProvider).filePreviewPage(widget.documentId, page);
          if (!mounted) return;
          setState(() => _pages[page] = bytes);
        }
      }
    } on ApiException catch (error) {
      if (mounted) setState(() => _error = error.message);
    }
  }

  @override
  Widget build(BuildContext context) {
    final size = MediaQuery.sizeOf(context);
    final wide = size.width >= 700;
    final preview = _preview;
    return Dialog(
      insetPadding: wide ? const EdgeInsets.all(24) : EdgeInsets.zero,
      child: SizedBox(
        width: wide ? 880 : size.width,
        height: wide ? 640 : size.height,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            ListTile(
              leading: Icon(fileIcon(preview?.fileType)),
              title: Text(widget.filename, maxLines: 1, overflow: TextOverflow.ellipsis),
              subtitle: Text(_subtitle(preview)),
              trailing: IconButton(
                tooltip: 'Close',
                icon: const Icon(Icons.close),
                onPressed: () => Navigator.pop(context),
              ),
            ),
            if (preview?.note != null)
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 0, 16, 8),
                child: Text(preview!.note!, style: Theme.of(context).textTheme.bodySmall),
              ),
            Expanded(child: _body(context)),
          ],
        ),
      ),
    );
  }

  String _subtitle(FilePreview? preview) {
    if (preview == null) return 'Loading preview…';
    return switch (preview.kind) {
      'spreadsheet' => '${preview.sheets.length} sheet${preview.sheets.length == 1 ? '' : 's'}',
      'slides' => '${preview.slides.length} slide${preview.slides.length == 1 ? '' : 's'}',
      'pdf' => '${preview.pageCount} page${preview.pageCount == 1 ? '' : 's'}',
      'document' => 'Document',
      _ => 'No formatted preview',
    };
  }

  Widget _body(BuildContext context) {
    if (_error != null) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Text('$_error', textAlign: TextAlign.center),
        ),
      );
    }
    final preview = _preview;
    if (preview == null) return const Center(child: CircularProgressIndicator());
    return switch (preview.kind) {
      'spreadsheet' => _sheets(preview),
      'document' => _document(preview),
      'slides' => _slides(preview),
      'pdf' => _pdf(preview),
      _ => const Center(child: Text('This file type has no formatted preview.')),
    };
  }

  Widget _sheets(FilePreview preview) {
    if (preview.sheets.isEmpty) return const Center(child: Text('This spreadsheet is empty.'));
    if (preview.sheets.length == 1) return _sheetTable(preview.sheets.single);
    return DefaultTabController(
      length: preview.sheets.length,
      child: Column(
        children: [
          TabBar(isScrollable: true, tabs: [for (final sheet in preview.sheets) Tab(text: sheet.name)]),
          Expanded(child: TabBarView(children: [for (final sheet in preview.sheets) _sheetTable(sheet)])),
        ],
      ),
    );
  }

  Widget _sheetTable(PreviewSheet sheet) {
    if (sheet.rows.isEmpty) return Center(child: Text('${sheet.name} is empty.'));
    final header = sheet.rows.first.map((cell) => '${cell ?? ''}').toList();
    final body = sheet.rows.skip(1);
    return Scrollbar(
      child: SingleChildScrollView(
        scrollDirection: Axis.horizontal,
        child: SingleChildScrollView(
          child: DataTable(
            columns: [for (final name in header) DataColumn(label: Text(name.isEmpty ? ' ' : name))],
            rows: [
              for (final row in body)
                DataRow(
                  cells: [
                    for (var i = 0; i < header.length; i++)
                      DataCell(Text(i < row.length && row[i] != null ? '${row[i]}' : '')),
                  ],
                ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _document(FilePreview preview) {
    final theme = Theme.of(context);
    return ListView(
      padding: const EdgeInsets.fromLTRB(20, 0, 20, 24),
      children: [
        for (final block in preview.blocks)
          if (block.type == 'heading')
            Padding(
              padding: const EdgeInsets.only(top: 12, bottom: 4),
              child: Text(block.text, style: _heading(theme, block.level)),
            )
          else if (block.type == 'bullet')
            Padding(padding: const EdgeInsets.only(left: 8, bottom: 4), child: Text('• ${block.text}'))
          else if (block.type == 'table')
            _plainTable(block.rows)
          else
            Padding(padding: const EdgeInsets.only(bottom: 8), child: Text(block.text)),
      ],
    );
  }

  TextStyle? _heading(ThemeData theme, int level) => switch (level) {
    0 || 1 => theme.textTheme.headlineSmall,
    2 => theme.textTheme.titleLarge,
    _ => theme.textTheme.titleMedium,
  };

  Widget _plainTable(List<List<String>> rows) {
    if (rows.isEmpty) return const SizedBox.shrink();
    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      child: DataTable(
        columns: [for (final cell in rows.first) DataColumn(label: Text(cell.isEmpty ? ' ' : cell))],
        rows: [
          for (final row in rows.skip(1))
            DataRow(cells: [for (var i = 0; i < rows.first.length; i++) DataCell(Text(i < row.length ? row[i] : ''))]),
        ],
      ),
    );
  }

  Widget _slides(FilePreview preview) {
    return ListView(
      padding: const EdgeInsets.fromLTRB(16, 0, 16, 24),
      children: [
        for (final slide in preview.slides)
          Card(
            margin: const EdgeInsets.only(bottom: 12),
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('Slide ${slide.number}', style: Theme.of(context).textTheme.labelMedium),
                  const SizedBox(height: 4),
                  Text(slide.title, style: Theme.of(context).textTheme.titleLarge),
                  for (final bullet in slide.bullets)
                    Padding(padding: const EdgeInsets.only(top: 6), child: Text('• $bullet')),
                  if (slide.notes.isNotEmpty)
                    Padding(
                      padding: const EdgeInsets.only(top: 12),
                      child: Text('Notes: ${slide.notes}', style: Theme.of(context).textTheme.bodySmall),
                    ),
                ],
              ),
            ),
          ),
      ],
    );
  }

  Widget _pdf(FilePreview preview) {
    if (preview.pageCount == 0) return const Center(child: Text('This PDF has no pages.'));
    return ListView(
      padding: const EdgeInsets.fromLTRB(16, 0, 16, 24),
      children: [
        for (var page = 1; page <= preview.pageCount; page++)
          Padding(
            padding: const EdgeInsets.only(bottom: 16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Text('Page $page', style: Theme.of(context).textTheme.labelMedium),
                const SizedBox(height: 6),
                if (_pages[page] == null)
                  const SizedBox(height: 160, child: Center(child: CircularProgressIndicator()))
                else
                  Image.memory(_pages[page]!, fit: BoxFit.contain),
              ],
            ),
          ),
      ],
    );
  }
}
