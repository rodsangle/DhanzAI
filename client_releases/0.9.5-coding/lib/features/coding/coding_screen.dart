import 'dart:async';
import 'dart:math';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/api/api_client.dart';
import '../../core/providers.dart';

class CodingScreen extends ConsumerStatefulWidget {
  const CodingScreen({super.key});
  @override
  ConsumerState<CodingScreen> createState() => _CodingScreenState();
}

class _CodingScreenState extends ConsumerState<CodingScreen> {
  final _title = TextEditingController();
  final _instructions = TextEditingController();
  final _branch = TextEditingController();
  final _paths = TextEditingController();
  final _browsePath = TextEditingController();
  List<String> _models = [];
  List<Map<String, dynamic>> _repositories = [];
  List<Map<String, dynamic>> _projects = [];
  List<Map<String, dynamic>> _drafts = [];
  List<Map<String, dynamic>> _entries = [];
  Map<String, dynamic>? _selected;
  String? _model;
  String? _project;
  String _repository = '';
  String _runtime = 'web';
  bool _automatic = false;
  bool _busy = false;
  bool _loading = true;
  String? _error;
  String? _connectionNote;
  String? _requestKey;
  String? _fingerprint;
  Timer? _poll;
  int _epoch = 0;

  @override
  void initState() {
    super.initState();
    unawaited(_load());
    _poll = Timer.periodic(const Duration(seconds: 5), (_) {
      if (!_busy && _drafts.any((d) => d['project_status'] == 'queued' || d['project_status'] == 'running')) {
        unawaited(_refresh());
      }
    });
  }

  @override
  void dispose() {
    _poll?.cancel();
    _epoch++;
    for (final controller in [_title, _instructions, _branch, _paths, _browsePath]) {
      controller.dispose();
    }
    super.dispose();
  }

  Future<void> _load() async {
    try {
      final api = ref.read(apiClientProvider);
      final models = await api.builderModels();
      final projects = await api.builderProjects();
      List<Map<String, dynamic>> repositories = [];
      String? note;
      try {
        repositories = await api.codingRepositories();
      } on ApiException catch (error) {
        note = error.message;
      }
      if (!mounted) return;
      setState(() {
        _models = (models['models'] as List<dynamic>).cast<String>();
        _model ??= _models.firstOrNull;
        _projects = projects;
        _repositories = repositories;
        _connectionNote = note;
      });
      await _refresh();
    } on ApiException catch (error) {
      if (mounted) setState(() => _error = error.message);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _refresh() async {
    final epoch = ++_epoch;
    try {
      final drafts = await ref.read(apiClientProvider).codingDrafts();
      Map<String, dynamic>? selected;
      if (_selected != null) {
        selected = await ref.read(apiClientProvider).codingDetail(_selected!['id'] as String);
      }
      if (!mounted || epoch != _epoch) return;
      setState(() {
        _drafts = drafts;
        if (selected != null) _selected = selected;
      });
    } on ApiException catch (error) {
      if (mounted && epoch == _epoch) setState(() => _error = error.message);
    }
  }

  Future<void> _create() async {
    if (_busy || _model == null || _title.text.trim().isEmpty || _instructions.text.trim().length < 5) {
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    final fingerprint =
        '${_title.text}|${_instructions.text}|$_model|$_repository|${_branch.text}|${_paths.text}|$_project|$_runtime|$_automatic';
    if (_fingerprint != fingerprint || _requestKey == null) {
      _fingerprint = fingerprint;
      _requestKey = '${DateTime.now().microsecondsSinceEpoch}_${Random.secure().nextInt(1 << 30)}';
    }
    try {
      final created = await ref.read(apiClientProvider).codingCreate({
        'title': _title.text.trim(),
        'instructions': _instructions.text.trim(),
        'model': _model,
        'request_key': _requestKey,
        'repository': _repository,
        'base_branch': _branch.text.trim(),
        'paths': _paths.text.split(RegExp(r'[,\n]')).map((p) => p.trim()).where((p) => p.isNotEmpty).toSet().toList(),
        'project_id': _project,
        'runtime': _runtime,
        'kind': _runtime == 'python' ? 'agent' : 'app',
        'auto_repair': _automatic,
      });
      _requestKey = null;
      if (!mounted) return;
      setState(() => _selected = created);
      await _refresh();
    } on ApiException catch (error) {
      if (mounted) setState(() => _error = error.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _open(Map<String, dynamic> draft) async {
    try {
      final data = await ref.read(apiClientProvider).codingDetail(draft['id'] as String);
      if (mounted) {
        setState(() {
          _selected = data;
          _error = null;
        });
      }
    } on ApiException catch (error) {
      if (mounted) setState(() => _error = error.message);
    }
  }

  Future<void> _action(String action, [Map<String, dynamic> body = const {}]) async {
    if (_busy || _selected == null) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final data = await ref.read(apiClientProvider).codingAction(_selected!['id'] as String, action, body);
      if (!mounted) return;
      setState(() => _selected = data);
      await _refresh();
    } on ApiException catch (error) {
      if (mounted) setState(() => _error = error.message);
      await _refresh();
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _browse() async {
    if (_repository.isEmpty || _busy) return;
    try {
      final result = await ref
          .read(apiClientProvider)
          .codingSource(_repository, _browsePath.text.trim(), _branch.text.trim());
      if (mounted) {
        setState(() => _entries = (result['entries'] as List<dynamic>).cast<Map<String, dynamic>>());
      }
    } on ApiException catch (error) {
      if (mounted) setState(() => _error = error.message);
    }
  }

  Future<void> _read(Map<String, dynamic> entry) async {
    if (entry['type'] == 'dir') {
      _browsePath.text = entry['path'] as String;
      await _browse();
      return;
    }
    try {
      final result = await ref
          .read(apiClientProvider)
          .codingSource(_repository, entry['path'] as String, _branch.text.trim(), file: true);
      if (!mounted) return;
      await showDialog<void>(
        context: context,
        builder: (context) => AlertDialog(
          title: Text(entry['path'] as String),
          content: SizedBox(
            width: 850,
            child: SingleChildScrollView(child: SelectableText(result['content'] as String)),
          ),
          actions: [
            TextButton(
              onPressed: () {
                final selected = _paths.text
                    .split(RegExp(r'[,\n]'))
                    .map((s) => s.trim())
                    .where((s) => s.isNotEmpty)
                    .toSet();
                selected.add(entry['path'] as String);
                _paths.text = selected.join('\n');
                Navigator.pop(context);
              },
              child: const Text('Include file'),
            ),
            TextButton(onPressed: () => Navigator.pop(context), child: const Text('Close')),
          ],
        ),
      );
    } on ApiException catch (error) {
      if (mounted) setState(() => _error = error.message);
    }
  }

  Future<void> _edit(Map<String, dynamic> file) async {
    final controller = TextEditingController(text: file['content'] as String);
    final result = await showDialog<String>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(file['path'] as String),
        content: SizedBox(
          width: 900,
          height: 500,
          child: TextField(
            controller: controller,
            expands: true,
            maxLines: null,
            style: const TextStyle(fontFamily: 'monospace'),
            decoration: const InputDecoration(border: OutlineInputBorder()),
          ),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context), child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.pop(context, controller.text), child: const Text('Save for review')),
        ],
      ),
    );
    controller.dispose();
    if (!mounted || result == null || _selected == null) return;
    final files = (_selected!['files'] as List<dynamic>).cast<Map<String, dynamic>>();
    await _action('review', {
      'files': [
        for (final value in files)
          if (!(value['path'] as String).startsWith('.github/'))
            {'path': value['path'], 'content': value['path'] == file['path'] ? result : value['content']},
      ],
    });
  }

  Future<void> _publish() async {
    final selected = _selected;
    if (selected == null) return;
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Publish reviewed files?'),
        content: Text(
          'Create a new branch and draft pull request in ${selected['repository']} from ${selected['base_branch']}. '
          'This also adds the displayed GitHub Actions workflow and starts checks on GitHub. Runner usage may be billed by GitHub. No merge or deployment is performed.',
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Publish branch & draft PR')),
        ],
      ),
    );
    if (confirmed == true && mounted) await _action('publish', {'review_hash': selected['review_hash']});
  }

  Widget _details() {
    final draft = _selected!;
    final files = (draft['files'] as List<dynamic>? ?? []).cast<Map<String, dynamic>>();
    final diffs = (draft['diffs'] as List<dynamic>? ?? []).cast<Map<String, dynamic>>();
    final checks = draft['checks'] as Map<String, dynamic>?;
    final failedChecks = checks?['conclusion'] == 'failure';
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(draft['title'] as String, style: Theme.of(context).textTheme.titleLarge),
            Text(
              'Generation: ${draft['project_status']} · Draft: ${draft['status']} · Repairs: ${draft['repair_count']}/1',
            ),
            if ((draft['repository'] as String).isNotEmpty)
              SelectableText('${draft['repository']} · ${draft['base_branch']}\nBase commit: ${draft['base_sha']}'),
            if (draft['error'] != null)
              Text(draft['error'] as String, style: TextStyle(color: Theme.of(context).colorScheme.error)),
            if (draft['pull_url'] != null) SelectableText('Draft PR: ${draft['pull_url']}'),
            if (draft['branch'] != null) SelectableText('Branch: ${draft['branch']}'),
            if (checks != null) ...[
              Text('GitHub checks: ${checks['status']} · ${checks['conclusion'] ?? ''}'),
              if (checks['detail'] != null) Text(checks['detail'] as String),
              if (checks['url'] != null) SelectableText(checks['url'] as String),
              for (final note in (checks['annotations'] as List<dynamic>? ?? []))
                SelectableText('${(note as Map<String, dynamic>)["path"]}:${note['line']} ${note['message']}'),
              for (final job in (checks['jobs'] as List<dynamic>? ?? [])) ...[
                Text('${(job as Map<String, dynamic>)['name']}: ${job['conclusion']}'),
                for (final step in job['steps'] as List<dynamic>)
                  Text('  ${(step as Map<String, dynamic>)['name']}: ${step['conclusion']}'),
              ],
            ],
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                if (draft['project_status'] == 'complete' &&
                    ['generating', 'repairing', 'review'].contains(draft['status']))
                  OutlinedButton(
                    onPressed: _busy ? null : () => _action('review'),
                    child: const Text('Prepare file review'),
                  ),
                if (draft['status'] == 'review' && (draft['repository'] as String).isNotEmpty)
                  FilledButton(onPressed: _busy ? null : _publish, child: const Text('Publish & run GitHub checks')),
                if (draft['status'] == 'published')
                  OutlinedButton(
                    onPressed: _busy ? null : () => _action('checks'),
                    child: const Text('Refresh check results'),
                  ),
                if ((draft['project_status'] == 'failed' || failedChecks) && draft['repair_count'] == 0)
                  FilledButton(
                    onPressed: _busy ? null : () => _action('repair'),
                    child: const Text('Repair once with AI'),
                  ),
                TextButton(onPressed: () => context.go('/builder'), child: const Text('Project files & ZIP downloads')),
              ],
            ),
            for (final file in files)
              ExpansionTile(
                title: Text(file['path'] as String),
                trailing:
                    (file['path'] as String).startsWith('.github/') ||
                        draft['status'] == 'published' ||
                        draft['status'] == 'publishing'
                    ? null
                    : IconButton(
                        tooltip: 'Edit file for review',
                        onPressed: _busy ? null : () => _edit(file),
                        icon: const Icon(Icons.edit),
                      ),
                children: [
                  Padding(
                    padding: const EdgeInsets.all(8),
                    child: SelectableText(file['content'] as String, style: const TextStyle(fontFamily: 'monospace')),
                  ),
                ],
              ),
            for (final diff in diffs)
              ExpansionTile(
                title: Text('Diff: ${diff['path']}'),
                children: [
                  Padding(
                    padding: const EdgeInsets.all(8),
                    child: SelectableText(diff['diff'] as String, style: const TextStyle(fontFamily: 'monospace')),
                  ),
                ],
              ),
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(
      title: const Text('Codex coding workspace'),
      leading: IconButton(tooltip: 'Back', icon: const Icon(Icons.arrow_back), onPressed: () => context.go('/chat')),
      actions: [
        IconButton(tooltip: 'Refresh workspace', icon: const Icon(Icons.refresh), onPressed: _busy ? null : _load),
      ],
    ),
    body: _loading
        ? const Center(child: CircularProgressIndicator())
        : Center(
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 1100),
              child: ListView(
                padding: const EdgeInsets.all(20),
                children: [
                  const Text(
                    'Read selected GitHub files, create changes, review diffs, publish a draft PR and run checks on GitHub-hosted runners. AI uses your OpenAI API account. Generated code is never executed on the Dhanz server.',
                  ),
                  if (_error != null)
                    Padding(
                      padding: const EdgeInsets.all(12),
                      child: Text(_error!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
                    ),
                  if (_connectionNote != null) Text('GitHub connection: $_connectionNote'),
                  TextButton(
                    onPressed: () => context.go('/github'),
                    child: const Text('Connect/select GitHub repositories'),
                  ),
                  TextField(
                    controller: _title,
                    maxLength: 100,
                    decoration: const InputDecoration(labelText: 'Task title'),
                  ),
                  DropdownButtonFormField<String>(
                    initialValue: _project,
                    decoration: const InputDecoration(labelText: 'Existing project to repair or extend (optional)'),
                    items: [
                      const DropdownMenuItem<String>(value: '', child: Text('New project / repository task')),
                      for (final project in _projects.where((p) => !['queued', 'running'].contains(p['status'])))
                        DropdownMenuItem(
                          value: project['id'] as String,
                          child: Text('${project['name']} · ${project['status']}', overflow: TextOverflow.ellipsis),
                        ),
                    ],
                    isExpanded: true,
                    onChanged: _busy ? null : (value) => setState(() => _project = value == '' ? null : value),
                  ),
                  DropdownButtonFormField<String>(
                    initialValue: _repository,
                    decoration: const InputDecoration(labelText: 'Repository (optional for private project repair)'),
                    items: [
                      const DropdownMenuItem(value: '', child: Text('Private project only')),
                      for (final repository in _repositories)
                        DropdownMenuItem(
                          value: repository['full_name'] as String,
                          child: Text(repository['full_name'] as String),
                        ),
                    ],
                    onChanged: _busy
                        ? null
                        : (value) => setState(() {
                            _repository = value ?? '';
                            _entries = [];
                          }),
                  ),
                  if (_repository.isNotEmpty) ...[
                    TextField(
                      controller: _branch,
                      decoration: const InputDecoration(labelText: 'Base branch (blank = repository default)'),
                    ),
                    TextField(
                      controller: _browsePath,
                      decoration: const InputDecoration(labelText: 'Browse folder (blank = root)'),
                    ),
                    OutlinedButton(onPressed: _busy ? null : _browse, child: const Text('Browse repository')),
                    for (final entry in _entries)
                      ListTile(
                        dense: true,
                        leading: Icon(entry['type'] == 'dir' ? Icons.folder : Icons.description),
                        title: Text(entry['path'] as String),
                        onTap: () => _read(entry),
                      ),
                    TextField(
                      controller: _paths,
                      maxLines: 4,
                      decoration: const InputDecoration(
                        labelText: 'Source paths to include (up to 12; one per line)',
                        hintText: 'src/main.py\ntests/test_main.py',
                      ),
                    ),
                  ],
                  DropdownButtonFormField<String>(
                    initialValue: _runtime,
                    decoration: const InputDecoration(labelText: 'Build/test runtime'),
                    items: const [
                      DropdownMenuItem(value: 'web', child: Text('Web / Node.js 22')),
                      DropdownMenuItem(value: 'python', child: Text('Python 3.12 / unittest')),
                    ],
                    onChanged: _busy ? null : (value) => setState(() => _runtime = value ?? 'web'),
                  ),
                  DropdownButtonFormField<String>(
                    key: ValueKey(_model),
                    initialValue: _model,
                    isExpanded: true,
                    decoration: const InputDecoration(labelText: 'Available API model'),
                    items: [for (final model in _models) DropdownMenuItem(value: model, child: Text(model))],
                    onChanged: _busy ? null : (value) => setState(() => _model = value),
                  ),
                  TextField(
                    controller: _instructions,
                    minLines: 4,
                    maxLines: 10,
                    maxLength: 12000,
                    decoration: const InputDecoration(labelText: 'What should Codex build, change or repair?'),
                  ),
                  CheckboxListTile(
                    contentPadding: EdgeInsets.zero,
                    value: _automatic,
                    onChanged: _busy ? null : (value) => setState(() => _automatic = value ?? false),
                    title: const Text('Allow one automatic AI repair attempt'),
                    subtitle: const Text(
                      'May add one paid API request after a generation failure or a failed check refresh. Authentication/quota failures are not retried automatically. Repairs remain private until you review and publish.',
                    ),
                  ),
                  FilledButton.icon(
                    onPressed: _busy || _model == null ? null : _create,
                    icon: const Icon(Icons.code),
                    label: Text(_busy ? 'Working…' : 'Create coding draft'),
                  ),
                  const SizedBox(height: 20),
                  if (_selected != null) _details(),
                  Text('Your coding drafts', style: Theme.of(context).textTheme.titleLarge),
                  for (final draft in _drafts)
                    Card(
                      child: ListTile(
                        title: Text(draft['title'] as String),
                        subtitle: Text('${draft['project_status']} · ${draft['status']} · ${draft['repository']}'),
                        trailing: const Icon(Icons.chevron_right),
                        onTap: _busy ? null : () => _open(draft),
                      ),
                    ),
                ],
              ),
            ),
          ),
  );
}
