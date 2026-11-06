import 'dart:async';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:uuid/uuid.dart';

import '../../core/api/api_client.dart';
import '../../core/files.dart';
import 'preview_document.dart';
import 'project_preview.dart';

class AppSimulatorPanel extends StatefulWidget {
  const AppSimulatorPanel({super.key, required this.listProjects, required this.loadProject,
    required this.reviseProject, required this.downloadProject, this.initialProjectId});
  final Future<List<Map<String, dynamic>>> Function() listProjects;
  final Future<Map<String, dynamic>> Function(String) loadProject;
  final Future<Map<String, dynamic>> Function(String, String, String) reviseProject;
  final Future<Uint8List> Function(String) downloadProject;
  final String? initialProjectId;

  @override
  State<AppSimulatorPanel> createState() => _AppSimulatorPanelState();
}

class _AppSimulatorPanelState extends State<AppSimulatorPanel> {
  final _changes = TextEditingController();
  Timer? _timer;
  List<Map<String, dynamic>> _projects = [];
  Map<String, dynamic>? _project;
  String? _selected;
  String? _error;
  bool _loading = false;
  bool _updating = false;
  bool _phone = true;
  int _reset = 0;
  int _selection = 0;
  String? _revisionKey;

  @override
  void initState() {
    super.initState();
    _selected = widget.initialProjectId;
    _refresh();
    _timer = Timer.periodic(const Duration(seconds: 4), (_) => _refresh());
  }

  @override
  void dispose() {
    _timer?.cancel();
    _changes.dispose();
    super.dispose();
  }

  Future<void> _refresh() async {
    if (_loading || _updating) return;
    _loading = true;
    final generation = _selection;
    try {
      final projects = (await widget.listProjects()).where((p) => p['kind'] == 'app').toList();
      if (!mounted || generation != _selection) return;
      final selected = _selected ?? (projects.isEmpty ? null : projects.first['id'] as String);
      final project = selected == null ? null : await widget.loadProject(selected);
      if (!mounted || generation != _selection) return;
      setState(() {
        _projects = projects;
        _selected = selected;
        _project = project;
        _error = null;
      });
    } catch (error) {
      if (mounted && generation == _selection) {
        setState(() => _error = error is ApiException ? error.message : 'Unable to load simulator. Press Refresh.');
      }
    } finally {
      _loading = false;
    }
  }

  Future<void> _revise() async {
    final id = _selected;
    if (id == null || _updating || _changes.text.trim().length < 5) return;
    setState(() => _updating = true);
    _revisionKey ??= const Uuid().v4();
    try {
      final result = await widget.reviseProject(id, _changes.text.trim(), _revisionKey!);
      if (!mounted) return;
      setState(() {
        _selection++;
        _selected = result['id'] as String;
        _project = result;
        _projects = [result, ..._projects.where((p) => p['id'] != result['id'])];
        _changes.clear();
        _revisionKey = null;
        _error = null;
      });
    } catch (error) {
      if (mounted) setState(() => _error = error is ApiException ? error.message :
        'Build status is uncertain. Refresh the project list before retrying; no automatic retry was made.');
    } finally {
      if (mounted) setState(() => _updating = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final project = _project;
    final ready = project?['status'] == 'complete';
    final files = ((project?['files'] as List<dynamic>?) ?? []).cast<Map<String, dynamic>>();
    final paths = files.map((f) => f['path']).toSet();
    final entry = paths.contains('simulator/index.html') ? 'simulator/index.html' : 'index.html';
    final hasDemo = ready && paths.contains(entry);
    return LayoutBuilder(builder: (context, bounds) => SingleChildScrollView(child: SizedBox(
      height: bounds.maxHeight < 600 ? 600 : bounds.maxHeight, child: Column(children: [
      Padding(padding: const EdgeInsets.all(8), child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        const Text('Browser demo · simulated integrations', style: TextStyle(fontWeight: FontWeight.bold)),
        const Text('Interactive browser preview, not an Android emulator. No real vehicle actions.'),
        if (_projects.isNotEmpty) DropdownButton<String>(
          isExpanded: true,
          value: _projects.any((p) => p['id'] == _selected) ? _selected : null,
          hint: const Text('Select an app project'),
          items: [for (final p in _projects) DropdownMenuItem(value: p['id'] as String,
            child: Text('${p['name']} · ${p['status']}', overflow: TextOverflow.ellipsis))],
          onChanged: _updating ? null : (id) {
            setState(() { _selection++; _selected = id; _project = null; _revisionKey = null; });
            _refresh();
          }),
        Wrap(spacing: 4, children: [
          TextButton.icon(onPressed: () => setState(() => _phone = !_phone),
            icon: Icon(_phone ? Icons.phone_android : Icons.desktop_windows), label: Text(_phone ? 'Phone' : 'Desktop')),
          IconButton(tooltip: 'Reset simulator', onPressed: hasDemo ? () => setState(() => _reset++) : null,
            icon: const Icon(Icons.restart_alt)),
          IconButton(tooltip: 'Refresh simulator projects', onPressed: _refresh, icon: const Icon(Icons.refresh)),
          IconButton(tooltip: 'Download project source', onPressed: !ready || _selected == null ? null : () async {
            try {
              final bytes = await widget.downloadProject(_selected!);
              await saveBytes('Dhanz_app_source.zip', bytes, mimeType: 'application/zip');
            } catch (error) {
              if (mounted) setState(() => _error = error is ApiException ? error.message : 'Download failed.');
            }
          }, icon: const Icon(Icons.download)),
        ]),
        if (_error != null) Text(_error!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
      ])),
      const Divider(height: 1),
      Expanded(child: !hasDemo ? Center(child: Padding(padding: const EdgeInsets.all(16), child: Text(
        project == null ? 'Build an app in chat, then select it here.' :
        project['status'] == 'queued' || project['status'] == 'running' ? 'Building source and simulator… This panel checks progress automatically.' :
        project['status'] == 'error' ? '${project['error'] ?? 'Build failed.'} No automatic retry was made.' :
        'This project has no browser demo. Describe a change below asking Dhanz to add an interactive simulator.')))
        : LayoutBuilder(builder: (context, constraints) => Center(child: SizedBox(
          width: _phone ? 390 : constraints.maxWidth,
          child: ProjectPreview(key: ValueKey('$_selected:$_reset'),
            document: previewDocument(files, entryPath: entry), height: constraints.maxHeight))))),
      const Divider(height: 1),
      Padding(padding: const EdgeInsets.all(8), child: Column(children: [
        TextField(controller: _changes, minLines: 1, maxLines: 3, maxLength: 8000,
          enabled: !_updating, onChanged: (_) { _revisionKey = null; setState(() {}); },
          decoration: const InputDecoration(labelText: 'What should change?', hintText: 'Example: make the Lock button larger')),
        FilledButton.icon(onPressed: ready && !_updating && _changes.text.trim().length >= 5 ? _revise : null,
          icon: const Icon(Icons.auto_fix_high), label: Text(_updating ? 'Queuing…' : 'Update app & simulator')),
        const Text('Creates a revised project and preserves the original. Uses your AI API credits.'),
      ])),
    ]))));
  }
}
