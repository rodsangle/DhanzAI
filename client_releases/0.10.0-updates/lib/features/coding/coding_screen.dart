import 'dart:async';
import 'dart:convert';
import 'dart:math';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/api/api_client.dart';
import '../../core/providers.dart';
import '../auth/auth_controller.dart';
import 'coding_plan.dart';

class CodingScreen extends ConsumerStatefulWidget {
  const CodingScreen({super.key, this.seed});
  final Map<String, dynamic>? seed;
  @override
  ConsumerState<CodingScreen> createState() => _CodingScreenState();
}

class _CodingScreenState extends ConsumerState<CodingScreen> {
  final _instructions = TextEditingController();
  final _browsePath = TextEditingController();
  final _scroll = ScrollController();
  final _questionAnchor = GlobalKey();
  late final FocusNode _chatFocus = FocusNode(
    onKeyEvent: (node, event) {
      if (event is KeyDownEvent &&
          event.logicalKey == LogicalKeyboardKey.enter &&
          !HardwareKeyboard.instance.isShiftPressed) {
        _respond(_instructions.text);
        return KeyEventResult.handled;
      }
      return KeyEventResult.ignored;
    },
  );
  final CodingPlan _plan = CodingPlan();
  final List<({String role, String text})> _turns = [];
  final Set<String> _reportedProjects = {};
  String _chatContext = '';
  String? _contextNotice;
  bool _seedLoaded = false;
  bool _showBrowser = false;
  String? _activeDraft;
  String? _returnChatId;
  List<Map<String, dynamic>> _drafts = [];
  List<Map<String, dynamic>> _entries = [];
  Map<String, dynamic>? _selected;
  bool _discretion = false;
  bool _resolvingDefaults = false;
  bool _busy = false;
  bool _loading = true;
  String? _error;
  String? _connectionNote;
  String? _requestKey;
  String? _fingerprint;
  String? _createdFingerprint;
  Timer? _poll;
  int _epoch = 0;

  @override
  void initState() {
    super.initState();
    unawaited(_load());
    _poll = Timer.periodic(const Duration(seconds: 5), (_) {
      if (!_busy &&
          _drafts.any(
            (d) =>
                d['project_status'] == 'queued' ||
                d['project_status'] == 'running' ||
                (d['project_status'] == 'failed' &&
                    d['auto_repair'] == true &&
                    d['repair_count'] == 0 &&
                    d['status'] == 'generating'),
          )) {
        unawaited(_refresh());
      }
    });
  }

  @override
  void dispose() {
    _poll?.cancel();
    _epoch++;
    _instructions.dispose();
    _browsePath.dispose();
    _chatFocus.dispose();
    _scroll.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    try {
      final api = ref.read(apiClientProvider);
      final models = await api.builderModels();
      var discretion = false;
      try { discretion = await api.autonomyEnabled(); } on ApiException { /* Keep manual mode if preferences are unavailable. */ }
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
        _discretion = discretion;
        _plan.models = (models['models'] as List<dynamic>).cast<String>();
        _plan.projects = projects;
        _plan.repositories = repositories;
        if (_plan.model.isNotEmpty && !_plan.models.contains(_plan.model)) _plan.change('model');
        _connectionNote = note;
        _error = null;
      });
      await _loadSeed();
      await _refresh();
      if (_createdFingerprint == null) await _applyDiscretion();
    } on ApiException catch (error) {
      if (mounted) setState(() => _error = error.message);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _loadSeed() async {
    if (_seedLoaded) return;
    _seedLoaded = true;
    final seed = widget.seed;
    if (seed == null) return;
    final api = ref.read(apiClientProvider);
    final user = ref.read(authControllerProvider).value;
    if (user == null || seed['user_id'] != user.id || seed['server'] != api.baseUrl) {
      if (mounted) {
        setState(() => _contextNotice = 'Chat context was not imported because the account or server changed.');
      }
      return;
    }
    final task = seed['task'] as String? ?? '';
    if (task.trim().isNotEmpty) {
      _plan.start(task);
      _turns.add((role: 'user', text: task));
    }
    final id = seed['temporary'] == true ? null : seed['conversation_id'] as String?;
    if (id != null) {
      _returnChatId = id;
      try {
        final detail = await api.conversation(id);
        if (!mounted) return;
        if (ref.read(authControllerProvider).value?.id != user.id ||
            ref.read(apiClientProvider).baseUrl != seed['server']) {
          return;
        }
        if (!detail.summary.temporary) _chatContext = codingChatContext(detail.messages);
        _contextNotice = detail.summary.temporary
            ? 'Temporary chat history was not imported.'
            : 'Using a recent text excerpt from the selected chat. View or remove it below.';
      } on ApiException catch (error) {
        if (mounted) _contextNotice = 'Could not import the selected chat: ${error.message}';
      }
    }
    if (seed['temporary'] == true) {
      _contextNotice = 'Temporary chat history was not imported. Only the text you entered is used.';
    }
    if (seed['has_attachments'] == true) {
      _contextNotice = '${_contextNotice ?? ''} Attachments are not imported; select code files in the workspace.';
    }
    if (mounted) setState(() {});
  }

  Future<void> _refresh() async {
    final epoch = ++_epoch;
    try {
      final drafts = await ref.read(apiClientProvider).codingDrafts();
      Map<String, dynamic>? selected;
      if (_selected != null) selected = await ref.read(apiClientProvider).codingDetail(_selected!['id'] as String);
      if (!mounted || epoch != _epoch) return;
      setState(() {
        _drafts = drafts;
        if (selected != null) {
          _selected = selected;
          final status = selected['project_status'];
          final report = '${selected['project_id']}:$status';
          if (selected['id'] == _activeDraft &&
              ['complete', 'failed'].contains(status) &&
              _reportedProjects.add(report)) {
            _turns.add((
              role: 'assistant',
              text: status == 'complete'
                  ? 'The generated files are ready for review below. Build/test checks have not run unless their results are shown separately.'
                  : 'Generation failed: ${selected['error'] ?? 'No complete project was saved.'} You can review the error and request a repair below.',
            ));
          }
        }
      });
    } on ApiException catch (error) {
      if (mounted && epoch == _epoch) setState(() => _error = error.message);
    }
  }

  Future<void> _setDiscretion() async {
    try {
      await ref.read(apiClientProvider).setAutonomy(!_discretion);
      if (!mounted) return;
      setState(() => _discretion = !_discretion);
      await _applyDiscretion();
    } on ApiException catch (error) {
      if (mounted) setState(() => _error = error.message);
    }
  }

  Future<void> _applyDiscretion() async {
    if (!_discretion || _busy || _resolvingDefaults || _plan.task.isEmpty) return;
    _resolvingDefaults = true;
    final notes = _plan.useDiscretion();
    final taskAtStart = _plan.task;
    final repoAtStart = _plan.repository;
    bool stillCurrent() => mounted && _plan.task == taskAtStart && _plan.repository == repoAtStart;
    try {
      if (_plan.question?.key == 'paths' && _plan.repository.isNotEmpty) {
        final api = ref.read(apiClientProvider);
        final root = await api.codingSource(_plan.repository, '', _plan.branch);
        if (!stillCurrent()) return;
        final entries = ((root['entries'] as List<dynamic>?) ?? []).cast<Map<String, dynamic>>();
        final candidates = <Map<String, dynamic>>[...entries.where((e) => e['type'] == 'file')];
        final folders = entries.where((e) => e['type'] == 'dir' && ['src','lib','app'].contains(e['name'])).take(2);
        for (final folder in folders) {
          final child = await api.codingSource(_plan.repository, folder['path'] as String, _plan.branch);
          if (!stillCurrent()) return;
          candidates.addAll(((child['entries'] as List<dynamic>?) ?? []).cast<Map<String,dynamic>>().where((e) => e['type'] == 'file'));
        }
        final textFiles = candidates.where((e) => RegExp(r'\.(md|json|yaml|yml|dart|py|ts|tsx|js|jsx|html|css|txt)$', caseSensitive: false).hasMatch(e['path'] as String)).toList();
        final priorities = ['package.json','pubspec.yaml','requirements.txt','README.md','main.dart','main.py','index.html'];
        int rank(Map<String,dynamic> e) { final i = priorities.indexOf(e['name'] as String); return i < 0 ? 99 : i; }
        textFiles.sort((a,b) => rank(a).compareTo(rank(b)));
        _plan.paths = textFiles.take(12).map((e) => e['path'] as String).toList();
        if (_plan.paths.isNotEmpty || entries.isEmpty) {
          _plan.answer(_plan.paths.isEmpty ? 'none' : 'selected', choice: true);
          notes.add('Read context: ${_plan.paths.length} repository files');
          notes.addAll(_plan.useDiscretion());
        }
      }
      if (!mounted) return;
      setState(() {
        if (notes.isNotEmpty) _turns.add((role: 'assistant', text: 'Using discretion: ${notes.join('; ')}. You can change these choices.'));
      });
    } on ApiException catch (error) {
      if (mounted) setState(() => _error = error.message);
      return;
    } finally {
      _resolvingDefaults = false;
    }
    if (mounted && _plan.question == null) {
      try {
        final enabled = await ref.read(apiClientProvider).autonomyEnabled();
        if (!mounted) return;
        if (!enabled) { setState(() => _discretion = false); return; }
        await _create();
      } on ApiException catch (error) {
        if (mounted) setState(() => _error = error.message);
      }
    }
  }

  void _respond(String text, {CodingChoice? choice}) {
    if (_busy || _resolvingDefaults || (text.trim().isEmpty && choice == null)) return;
    if (_discretion && _plan.question == null && choice == null &&
        !isCodingWorkRequest(text)) {
      setState(() => _turns.add((role: 'assistant', text: 'No new build started. The latest saved status is shown below. Describe a coding change or say Start coding to begin work.')));
      unawaited(_refresh());
      return;
    }
    final question = _plan.question;
    if (choice != null) _chatFocus.unfocus();
    if (question == null &&
        choice == null &&
        ['start', 'start coding', 'generate', 'go ahead', 'create draft'].contains(text.trim().toLowerCase())) {
      setState(() {
        _turns.add((role: 'user', text: text.trim()));
        _instructions.clear();
      });
      unawaited(_create());
      return;
    }
    setState(() {
      if (question != null) _turns.add((role: 'assistant', text: question.text));
      _turns.add((role: 'user', text: choice?.label ?? text.trim()));
      final notice = _plan.answer(choice?.value ?? text, choice: choice != null);
      if (notice != null) _turns.add((role: 'assistant', text: notice));
      if (question?.key == 'paths' && choice?.value == 'browse') _showBrowser = true;
      _instructions.clear();
      _error = null;
    });
    unawaited(_applyDiscretion());
    WidgetsBinding.instance.addPostFrameCallback((_) {
      final anchor = _questionAnchor.currentContext;
      if (mounted && anchor != null) {
        unawaited(Scrollable.ensureVisible(anchor, duration: const Duration(milliseconds: 200), alignment: 0.05));
      }
    });
  }

  Future<void> _create() async {
    if (_busy || _plan.question != null) return;
    String instructions;
    try {
      instructions = _plan.instructions(_chatContext);
    } on FormatException catch (error) {
      setState(() => _error = error.message);
      return;
    }
    final title = _plan.task.replaceAll(RegExp(r'\s+'), ' ').trim();
    final data = <String, dynamic>{
      'title': title.length > 100 ? title.substring(0, 100) : title,
      'instructions': instructions,
      'model': _plan.model,
      'repository': _plan.repository,
      'base_branch': _plan.branch,
      'paths': _plan.paths,
      'project_id': _plan.projectId,
      'runtime': _plan.runtime,
      'workdir': _plan.workdir,
      'kind': _plan.runtime == 'python' ? 'agent' : 'app',
      'auto_repair': _plan.automatic,
    };
    final fingerprint = jsonEncode(data);
    if (_createdFingerprint == fingerprint) {
      setState(
        () => _turns.add((
          role: 'assistant',
          text: 'A draft for these settings is already saved below. Add a requirement or change an answer before starting a new draft.',
        )),
      );
      return;
    }
    if (_fingerprint != fingerprint || _requestKey == null) {
      _fingerprint = fingerprint;
      _requestKey = '${DateTime.now().microsecondsSinceEpoch}_${Random.secure().nextInt(1 << 30)}';
    }
    data['request_key'] = _requestKey;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final created = await ref.read(apiClientProvider).codingCreate(data);
      _requestKey = null;
      _createdFingerprint = fingerprint;
      if (!mounted) return;
      setState(() {
        _selected = created;
        _activeDraft = created['id'] as String;
        _turns.add((
          role: 'assistant',
          text: 'Coding draft saved. Its generation status and files appear below. Generation continues if you leave this page; GitHub publishing still needs your file review.',
        ));
      });
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
    if (_plan.repository.isEmpty || _busy) return;
    try {
      final result = await ref
          .read(apiClientProvider)
          .codingSource(_plan.repository, _browsePath.text.trim(), _plan.branch);
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
          .codingSource(_plan.repository, entry['path'] as String, _plan.branch, file: true);
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
                setState(() => _plan.paths = {..._plan.paths, entry['path'] as String}.toList());
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

  Widget _bubble(String role, String text) => Align(
    alignment: role == 'user' ? Alignment.centerRight : Alignment.centerLeft,
    child: Container(
      margin: const EdgeInsets.symmetric(vertical: 5),
      padding: const EdgeInsets.all(14),
      constraints: const BoxConstraints(maxWidth: 820),
      decoration: BoxDecoration(
        color: role == 'user'
            ? Theme.of(context).colorScheme.primaryContainer
            : Theme.of(context).colorScheme.surfaceContainer,
        borderRadius: BorderRadius.circular(16),
      ),
      child: SelectableText(text),
    ),
  );

  Future<void> _connect() async {
    await context.push<void>('/github');
    if (mounted) await _load();
  }

  void _changeTask() {
    final task = _plan.task;
    setState(() {
      _plan.reset();
      _instructions.text = task;
    });
  }

  Widget _questionCards() {
    final question = _plan.question;
    if (question == null) {
      return Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _bubble(
            'assistant',
            'Ready to create a private coding draft. Review the choices below, add any final requirements in the chat box, then choose Start coding. This starts the paid model request; it does not publish to GitHub.',
          ),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(14),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(_plan.task),
                  Text('Destination: ${_plan.repository.isEmpty ? 'Private project' : _plan.repository}'),
                  if (_plan.projectId != null)
                    Text(
                      'Source project: ${_plan.projects.where((p) => p['id'] == _plan.projectId).firstOrNull?['name'] ?? 'Selected project'}',
                    ),
                  Text(
                    'Base: ${_plan.branch.isEmpty ? 'Repository default' : _plan.branch} · Source files: ${_plan.paths.length}',
                  ),
                  Text(
                    'Project/checks: ${_plan.runtime} · Folder: ${_plan.workdir.isEmpty ? 'Repository root' : _plan.workdir}',
                  ),
                  Text(
                    'API model: ${_plan.model} · Automatic repair: ${_plan.automatic ? 'Once (may add API usage)' : 'Off'}',
                  ),
                  if (_plan.extraRequirements.isNotEmpty)
                    Text('Additional requirements: ${_plan.extraRequirements.join('; ')}'),
                  Wrap(
                    spacing: 8,
                    children: [
                      FilledButton.icon(
                        onPressed: _busy ? null : _create,
                        icon: const Icon(Icons.code),
                        label: Text(_busy ? 'Saving draft…' : 'Start coding'),
                      ),
                      TextButton(onPressed: _busy ? null : _changeTask, child: const Text('Edit request')),
                      for (final key in [
                        'goal',
                        if (_plan.goal == 'repair') 'project',
                        'repository',
                        if (_plan.repository.isNotEmpty) ...['branch', 'paths', 'workdir'],
                        'runtime',
                        'model',
                        'repair',
                      ])
                        TextButton(
                          onPressed: _busy ? null : () => setState(() => _plan.change(key)),
                          child: Text(
                            'Change ${{'goal': 'task type', 'project': 'source project', 'repository': 'destination', 'branch': 'base branch', 'paths': 'source files', 'workdir': 'check folder', 'runtime': 'project type', 'model': 'model', 'repair': 'repair option'}[key]}',
                          ),
                        ),
                    ],
                  ),
                ],
              ),
            ),
          ),
        ],
      );
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _bubble('assistant', question.text),
        for (var index = 0; index < question.choices.length; index++)
          Card(
            child: ListTile(
              enabled: !_busy,
              leading: CircleAvatar(radius: 15, child: Text('${index + 1}')),
              title: Text(question.choices[index].label),
              subtitle: Text(question.choices[index].explanation),
              trailing: const Icon(Icons.chevron_right),
              onTap: _busy
                  ? null
                  : () {
                      final choice = question.choices[index];
                      if (choice.value == 'connect' && question.key == 'repository') {
                        unawaited(_connect());
                        return;
                      }
                      _respond(choice.value, choice: choice);
                    },
            ),
          ),
        TextButton(onPressed: _busy ? null : _changeTask, child: const Text('Edit request and restart setup')),
        if (question.key == 'paths' && _showBrowser) ...[
          TextField(
            controller: _browsePath,
            decoration: const InputDecoration(labelText: 'Repository folder (blank = root)'),
          ),
          OutlinedButton(onPressed: _busy ? null : _browse, child: const Text('Browse files')),
          for (final entry in _entries)
            ListTile(
              dense: true,
              leading: Icon(entry['type'] == 'dir' ? Icons.folder : Icons.description),
              title: Text(entry['path'] as String),
              onTap: () => _read(entry),
            ),
        ],
      ],
    );
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(
      title: const Text('Chat with Codex'),
      leading: IconButton(
        tooltip: 'Back',
        icon: const Icon(Icons.arrow_back),
        onPressed: () => context.go(_returnChatId == null ? '/chat' : '/chat/$_returnChatId'),
      ),
      actions: [
        IconButton(tooltip: _discretion ? 'Use discretion: on' : 'Use discretion: off',
          isSelected: _discretion, icon: const Icon(Icons.auto_awesome), onPressed: _busy ? null : _setDiscretion),
        IconButton(tooltip: 'Refresh workspace', icon: const Icon(Icons.refresh), onPressed: _busy ? null : _load),
      ],
    ),
    body: _loading
        ? const Center(child: CircularProgressIndicator())
        : Column(
            children: [
              Expanded(
                child: Center(
                  child: ConstrainedBox(
                    constraints: const BoxConstraints(maxWidth: 1000),
                    child: ListView(
                      controller: _scroll,
                      padding: const EdgeInsets.all(16),
                      children: [
                        const Text(
                          'Describe the task and answer one question at a time. Options explain their effects; you can also type an answer. Setup runs locally. AI starts when you choose Start coding.',
                        ),
                        if (_error != null)
                          Padding(
                            padding: const EdgeInsets.all(12),
                            child: Text(_error!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
                          ),
                        if (_connectionNote != null) Text('GitHub connection: $_connectionNote'),
                        if (_plan.models.isEmpty)
                          TextButton(onPressed: _busy ? null : _load, child: const Text('Retry model connection')),
                        if (_contextNotice != null) Text(_contextNotice!),
                        if (_chatContext.isNotEmpty)
                          ExpansionTile(
                            title: const Text('Included chat text (attachments excluded)'),
                            children: [
                              SelectableText(_chatContext),
                              TextButton(
                                onPressed: _busy
                                    ? null
                                    : () => setState(() {
                                        _chatContext = '';
                                        _contextNotice = 'Chat context removed.';
                                      }),
                                child: const Text('Remove chat context'),
                              ),
                            ],
                          ),
                        for (final turn in _turns) _bubble(turn.role, turn.text),
                        KeyedSubtree(key: _questionAnchor, child: _questionCards()),
                        if (_selected != null) _details(),
                        const SizedBox(height: 16),
                        Text('Saved coding drafts', style: Theme.of(context).textTheme.titleLarge),
                        for (final draft in _drafts)
                          Card(
                            child: ListTile(
                              title: Text(draft['title'] as String),
                              subtitle: Text(
                                '${draft['project_status']} · ${draft['status']} · ${draft['repository']}',
                              ),
                              trailing: const Icon(Icons.chevron_right),
                              onTap: _busy ? null : () => _open(draft),
                            ),
                          ),
                      ],
                    ),
                  ),
                ),
              ),
              SafeArea(
                top: false,
                child: Padding(
                  padding: const EdgeInsets.all(12),
                  child: Center(
                    child: ConstrainedBox(
                      constraints: const BoxConstraints(maxWidth: 1000),
                      child: Row(
                        crossAxisAlignment: CrossAxisAlignment.end,
                        children: [
                          Expanded(
                            child: TextField(
                              controller: _instructions,
                              focusNode: _chatFocus,
                              textInputAction: TextInputAction.newline,
                              minLines: 1,
                              maxLines: 5,
                              maxLength: 6000,
                              onSubmitted: _busy ? null : (text) => _respond(text),
                              decoration: InputDecoration(
                                hintText: _plan.question?.hint ?? 'Add a final requirement…',
                                border: const OutlineInputBorder(),
                                counterText: '',
                              ),
                            ),
                          ),
                          const SizedBox(width: 8),
                          IconButton.filled(
                            tooltip: 'Send',
                            onPressed: _busy ? null : () => _respond(_instructions.text),
                            icon: const Icon(Icons.arrow_upward),
                          ),
                        ],
                      ),
                    ),
                  ),
                ),
              ),
            ],
          ),
  );
}
