import 'dart:async';
import 'dart:math';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/providers.dart';

class OperationsScreen extends ConsumerStatefulWidget {
  const OperationsScreen({super.key});
  @override
  ConsumerState<OperationsScreen> createState() => _OperationsScreenState();
}

class _OperationsScreenState extends ConsumerState<OperationsScreen> {
  final _server = TextEditingController(text: 'AWS Dhanz');
  final _repo = TextEditingController();
  final _branch = TextEditingController(text: 'main');
  final _hours = TextEditingController(text: '24');
  final _uses = TextEditingController(text: '10');
  final Map<String, String> _keys = {};
  Map<String, dynamic> _data = {};
  String? _error;
  bool _busy = false;
  Timer? _poll;

  List<Map<String, dynamic>> _rows(String key) => ((_data[key] as List<dynamic>?) ?? []).cast<Map<String, dynamic>>();

  @override
  void initState() {
    super.initState();
    unawaited(_load());
    _poll = Timer.periodic(const Duration(seconds: 10), (_) {
      if (!_busy) unawaited(_load());
    });
  }

  @override
  void dispose() {
    _poll?.cancel();
    for (final controller in [_server, _repo, _branch, _hours, _uses]) {
      controller.dispose();
    }
    super.dispose();
  }

  Future<void> _load() async {
    try {
      final data = await ref.read(apiClientProvider).operations();
      if (mounted) {
        setState(() {
          _data = data;
          _error = null;
        });
      }
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
    }
  }

  Future<void> _action(String path, Map<String, dynamic> body, {bool pairing = false}) async {
    setState(() => _busy = true);
    try {
      final result = await ref.read(apiClientProvider).operationAction(path, body);
      if (!mounted) return;
      if (pairing) {
        await showDialog<void>(
          context: context,
          builder: (context) => AlertDialog(
            title: const Text('Pair your AWS server'),
            content: SizedBox(
              width: 520,
              child: SingleChildScrollView(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text(
                      'This token is shown once. Paste it only into the hidden pairing prompt in your AWS terminal. Do not paste it into chat.',
                    ),
                    const SizedBox(height: 12),
                    SelectableText(result['token'] as String),
                    TextButton.icon(
                      onPressed: () async {
                        await Clipboard.setData(ClipboardData(text: result['token'] as String));
                      },
                      icon: const Icon(Icons.copy),
                      label: const Text('Copy pairing token'),
                    ),
                    const Text(
                      'Run the server companion setup, then refresh this page to authorize its named tasks. Disconnect this server if you lose the token.',
                    ),
                  ],
                ),
              ),
            ),
            actions: [TextButton(onPressed: () => Navigator.pop(context), child: const Text('Done'))],
          ),
        );
      }
      await _load();
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _authorize(Map<String, dynamic> body, String description) async {
    final hours = int.tryParse(_hours.text);
    final uses = int.tryParse(_uses.text);
    if (hours == null || hours < 1 || hours > 168 || uses == null || uses < 1 || uses > 100) {
      setState(() => _error = 'Use 1–168 hours and 1–100 executions.');
      return;
    }
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Authorize automatic actions'),
        content: Text(
          '$description\n\nAllow up to $uses executions over the next $hours hours without another approval dialog. You can revoke permission here. Revocation stops queued tasks; a task already started may finish.',
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Authorize')),
        ],
      ),
    );
    if (confirmed == true && mounted) {
      await _action('grants', {...body, 'hours': hours, 'uses': uses, 'authorize': true});
    }
  }

  Future<void> _run(Map<String, dynamic> grant) async {
    final id = grant['id'] as String;
    final key = _keys.putIfAbsent(
      id,
      () => List.generate(32, (_) => Random.secure().nextInt(16).toRadixString(16)).join(),
    );
    await _action('run', {'grant_id': id, 'request_key': key});
    // Keep the key after uncertain network errors. A retry must not enqueue a second command.
    if (_error == null) _keys.remove(id);
  }

  Widget _field(TextEditingController controller, String label) => Padding(
    padding: const EdgeInsets.symmetric(vertical: 6),
    child: TextField(
      controller: controller,
      enabled: !_busy,
      decoration: InputDecoration(labelText: label),
    ),
  );

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(
      title: const Text('Connected operations'),
      leading: IconButton(icon: const Icon(Icons.arrow_back), onPressed: () => context.go('/chat')),
      actions: [IconButton(onPressed: _busy ? null : _load, icon: const Icon(Icons.refresh))],
    ),
    body: Center(
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 820),
        child: ListView(
          padding: const EdgeInsets.all(20),
          children: [
            const Text(
              'Connect once, then let Dhanz carry out tasks within your standing permissions. Each permission names the target, expires, and has an execution limit.',
            ),
            if (_busy) const LinearProgressIndicator(),
            if (_error != null) Padding(padding: const EdgeInsets.all(8), child: SelectableText(_error!)),
            const SizedBox(height: 16),
            Text('Permission limits', style: Theme.of(context).textTheme.titleLarge),
            _field(_hours, 'Hours until expiry (1–168)'),
            _field(_uses, 'Maximum executions (1–100)'),
            const SizedBox(height: 16),
            Text('AWS server', style: Theme.of(context).textTheme.titleLarge),
            _field(_server, 'Connection name'),
            OutlinedButton.icon(
              onPressed: _busy ? null : () => _action('servers', {'name': _server.text.trim()}, pairing: true),
              icon: const Icon(Icons.link),
              label: const Text('Create server pairing token'),
            ),
            for (final server in _rows('servers'))
              if (server['revoked'] != true)
                Card(
                  child: Padding(
                    padding: const EdgeInsets.all(12),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(server['name'] as String, style: Theme.of(context).textTheme.titleMedium),
                        Text('Last connected: ${server['last_seen'] ?? 'Waiting for companion setup'}'),
                        for (final dynamic task in server['tasks'] as List<dynamic>)
                          ListTile(
                            contentPadding: EdgeInsets.zero,
                            title: Text(task['name'] as String),
                            subtitle: Text(task['description'] as String),
                            trailing: TextButton(
                              onPressed: _busy
                                  ? null
                                  : () => _authorize({
                                      'kind': 'server_task',
                                      'target': server['id'],
                                      'task': task['name'],
                                    }, '${server['name']}: ${task['description']}'),
                              child: const Text('Authorize'),
                            ),
                          ),
                        TextButton(
                          onPressed: _busy ? null : () => _action('servers/${server['id']}/revoke', {}),
                          child: const Text('Disconnect server'),
                        ),
                      ],
                    ),
                  ),
                ),
            const SizedBox(height: 16),
            Text('Automatic GitHub publication', style: Theme.of(context).textTheme.titleLarge),
            const Text(
              'New coding drafts for this repository and base branch will publish automatically as separate branches and draft pull requests, including the workspace check workflow. This does not merge pull requests or deploy code.',
            ),
            TextButton(
              onPressed: () => context.push('/github'),
              child: const Text('Connect GitHub or select repositories'),
            ),
            _field(_repo, 'Repository: owner/name'),
            _field(_branch, 'Base branch'),
            OutlinedButton(
              onPressed: _busy
                  ? null
                  : () => _authorize(
                      {'kind': 'github_publish', 'target': _repo.text.trim(), 'branch': _branch.text.trim()},
                      'Automatically publish future coding drafts to ${_repo.text.trim()} from ${_branch.text.trim()}, including a checks workflow.',
                    ),
              child: const Text('Authorize automatic draft pull requests'),
            ),
            const SizedBox(height: 16),
            Text('Standing permissions', style: Theme.of(context).textTheme.titleLarge),
            for (final grant in _rows('grants'))
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(12),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('${grant['kind']} — ${grant['target']}'),
                      Text('${grant['scope']}\n${grant['remaining']} executions left. Expires ${grant['expires_at']}'),
                      Wrap(
                        spacing: 8,
                        children: [
                          if (grant['active'] == true && grant['kind'] == 'server_task')
                            TextButton(
                              onPressed:
                                  _busy ||
                                      _rows('jobs').any(
                                        (j) =>
                                            j['grant_id'] == grant['id'] &&
                                            const ['queued', 'executing'].contains(j['status']),
                                      )
                                  ? null
                                  : () => _run(grant),
                              child: const Text('Run task now'),
                            ),
                          if (grant['active'] == true)
                            TextButton(
                              onPressed: _busy ? null : () => _action('grants/${grant['id']}/revoke', {}),
                              child: const Text('Revoke'),
                            ),
                        ],
                      ),
                    ],
                  ),
                ),
              ),
            const SizedBox(height: 16),
            Text('Activity', style: Theme.of(context).textTheme.titleLarge),
            for (final job in _rows('jobs'))
              ListTile(
                title: Text('${job['task']}: ${job['status']}'),
                subtitle: Text('${job['created_at']}\n${job['detail']}'),
              ),
            const Text(
              'After connecting, ask in chat: “Check my AWS server health” or “Restart Dhanz.” Check the activity result before assuming a task completed.',
            ),
          ],
        ),
      ),
    ),
  );
}
