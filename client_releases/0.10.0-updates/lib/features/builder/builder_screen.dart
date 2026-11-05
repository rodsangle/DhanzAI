import 'dart:async';
import 'dart:math';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/api/api_client.dart';
import '../../core/files.dart';
import '../../core/providers.dart';
import 'preview_document.dart';
import 'project_preview.dart';

class BuilderScreen extends ConsumerStatefulWidget {
  const BuilderScreen({super.key});
  @override
  ConsumerState<BuilderScreen> createState() => _BuilderScreenState();
}

class _BuilderScreenState extends ConsumerState<BuilderScreen> {
  final _name = TextEditingController();
  final _prompt = TextEditingController();
  List<String> _models = [];
  List<Map<String, dynamic>> _projects = [];
  String? _model;
  String _kind = 'app';
  String? _error;
  String? _details;
  bool _loading = true;
  bool _creating = false;
  Timer? _poll;
  int _epoch = 0;
  String? _requestKey;
  String? _requestFingerprint;

  @override
  void initState() {
    super.initState();
    unawaited(_load());
    _poll = Timer.periodic(const Duration(seconds: 5), (_) {
      if (_projects.any((p) => p['status'] == 'queued' || p['status'] == 'running')) {
        unawaited(_loadProjects());
      }
    });
  }

  @override
  void dispose() {
    _poll?.cancel();
    _epoch++;
    _name.dispose();
    _prompt.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    try {
      final data = await ref.read(apiClientProvider).builderModels();
      if (!mounted) return;
      setState(() {
        _models = (data['models'] as List<dynamic>).cast<String>();
        _model = _models.firstOrNull;
        _details = data['detail'] as String?;
      });
      await _loadProjects();
    } on ApiException catch (error) {
      if (mounted) setState(() => _error = error.message);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _loadProjects() async {
    final epoch = ++_epoch;
    try {
      final projects = await ref.read(apiClientProvider).builderProjects();
      if (mounted && epoch == _epoch) {
        setState(() {
          _projects = projects;
          _error = null;
        });
      }
    } on ApiException catch (error) {
      if (mounted && epoch == _epoch) setState(() => _error = error.message);
    }
  }

  Future<void> _create() async {
    if (_creating || _model == null || _name.text.trim().isEmpty || _prompt.text.trim().length < 5) {
      return;
    }
    setState(() {
      _creating = true;
      _error = null;
    });
    final fingerprint = '$_kind|${_name.text.trim()}|${_prompt.text.trim()}|$_model';
    if (_requestFingerprint != fingerprint || _requestKey == null) {
      _requestFingerprint = fingerprint;
      _requestKey = '${DateTime.now().microsecondsSinceEpoch}_${Random.secure().nextInt(1 << 30)}';
    }
    final requestKey = _requestKey!;
    try {
      await ref.read(apiClientProvider).createBuilderProject({
        'name': _name.text.trim(),
        'kind': _kind,
        'prompt': _prompt.text.trim(),
        'model': _model,
        'request_key': requestKey,
      });
      _requestKey = null;
      await _loadProjects();
    } on ApiException catch (error) {
      if (mounted) setState(() => _error = error.message);
    } finally {
      if (mounted) setState(() => _creating = false);
    }
  }

  Future<void> _download(Map<String, dynamic> project) async {
    try {
      final bytes = await ref.read(apiClientProvider).downloadBuilderProject(project['id'] as String);
      if (!mounted) return;
      final name = (project['name'] as String).replaceAll(RegExp(r'[^A-Za-z0-9_-]'), '_');
      await saveBytes('$name.zip', bytes);
    } on ApiException catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(error.message)));
      }
    }
  }

  Future<void> _view(Map<String, dynamic> project, {bool preview = false}) async {
    try {
      final data = await ref.read(apiClientProvider).builderProject(project['id'] as String);
      final files = (data['files'] as List<dynamic>).cast<Map<String, dynamic>>();
      if (!mounted) return;
      await showDialog<void>(
        context: context,
        builder: (context) => Dialog(
          child: SizedBox(
            width: 900,
            height: 650,
            child: Column(
              children: [
                ListTile(
                  title: Text(project['name'] as String),
                  trailing: IconButton(
                    tooltip: 'Close',
                    icon: const Icon(Icons.close),
                    onPressed: () => Navigator.pop(context),
                  ),
                ),
                if (preview)
                  const Padding(
                    padding: EdgeInsets.all(8),
                    child: Text('Static preview only. Network and backend features are unavailable in this preview.'),
                  ),
                Expanded(
                  child: preview
                      ? SingleChildScrollView(child: ProjectPreview(document: previewDocument(files)))
                      : ListView(
                          children: [
                            for (final file in files)
                              ExpansionTile(
                                title: Text(file['path'] as String),
                                children: [
                                  Padding(
                                    padding: const EdgeInsets.all(12),
                                    child: SelectableText(
                                      file['content'] as String,
                                      style: const TextStyle(fontFamily: 'monospace'),
                                    ),
                                  ),
                                ],
                              ),
                          ],
                        ),
                ),
              ],
            ),
          ),
        ),
      );
    } on ApiException catch (error) {
      if (mounted) setState(() => _error = error.message);
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(
      title: const Text('App & agent builder'),
      leading: IconButton(tooltip: 'Back', icon: const Icon(Icons.arrow_back), onPressed: () => context.go('/chat')),
      actions: [IconButton(tooltip: 'Refresh builds', icon: const Icon(Icons.refresh), onPressed: _loadProjects)],
    ),
    body: Center(
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 1000),
        child: _loading
            ? const Center(child: CircularProgressIndicator())
            : ListView(
                padding: const EdgeInsets.all(20),
                children: [
                  Text(_details ?? 'Choose a connected model to create a project.'),
                  if (_error != null)
                    Padding(
                      padding: const EdgeInsets.symmetric(vertical: 12),
                      child: Text(_error!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
                    ),
                  if (_models.isEmpty) FilledButton(onPressed: _load, child: const Text('Retry model connection')),
                  TextField(
                    controller: _name,
                    maxLength: 100,
                    decoration: const InputDecoration(labelText: 'Project name'),
                  ),
                  DropdownButtonFormField<String>(
                    initialValue: _kind,
                    decoration: const InputDecoration(labelText: 'Create'),
                    items: const [
                      DropdownMenuItem(value: 'app', child: Text('Web app project')),
                      DropdownMenuItem(value: 'agent', child: Text('Python agent project')),
                    ],
                    onChanged: _creating ? null : (value) => setState(() => _kind = value ?? 'app'),
                  ),
                  const SizedBox(height: 12),
                  DropdownButtonFormField<String>(
                    key: ValueKey(_model),
                    initialValue: _model,
                    isExpanded: true,
                    decoration: const InputDecoration(labelText: 'Available API model'),
                    items: [for (final model in _models) DropdownMenuItem(value: model, child: Text(model))],
                    onChanged: _creating ? null : (value) => setState(() => _model = value),
                  ),
                  const SizedBox(height: 12),
                  TextField(
                    controller: _prompt,
                    minLines: 4,
                    maxLines: 10,
                    maxLength: 12000,
                    decoration: const InputDecoration(
                      labelText: 'What should it do?',
                      hintText: 'Describe the project. Use placeholders for credentials.',
                    ),
                  ),
                  FilledButton.icon(
                    onPressed: _creating || _model == null ? null : _create,
                    icon: Icon(_creating ? Icons.hourglass_top : Icons.code),
                    label: Text(_creating ? 'Queuing build…' : 'Create project'),
                  ),
                  const Padding(
                    padding: EdgeInsets.symmetric(vertical: 16),
                    child: Text(
                      'Builds continue when you leave this screen. Code is generated as files; it is not executed or deployed.',
                    ),
                  ),
                  for (final project in _projects)
                    Card(
                      child: Padding(
                        padding: const EdgeInsets.all(12),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(project['name'] as String, style: Theme.of(context).textTheme.titleMedium),
                            Text('${project['kind']} · ${project['model']} · ${project['status']}'),
                            if (project['summary'] != null) Text(project['summary'] as String),
                            if (project['error'] != null)
                              Text(
                                project['error'] as String,
                                style: TextStyle(color: Theme.of(context).colorScheme.error),
                              ),
                            if (project['status'] == 'complete')
                              Wrap(
                                spacing: 8,
                                children: [
                                  OutlinedButton(onPressed: () => _view(project), child: const Text('View files')),
                                  if (project['kind'] == 'app')
                                    OutlinedButton(
                                      onPressed: () => _view(project, preview: true),
                                      child: const Text('Preview'),
                                    ),
                                  FilledButton.icon(
                                    onPressed: () => _download(project),
                                    icon: const Icon(Icons.download),
                                    label: const Text('Download ZIP'),
                                  ),
                                ],
                              ),
                          ],
                        ),
                      ),
                    ),
                ],
              ),
      ),
    ),
  );
}
