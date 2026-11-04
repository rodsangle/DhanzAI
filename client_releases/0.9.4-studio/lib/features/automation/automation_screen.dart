import 'dart:async';
import 'dart:convert';
import 'dart:math' as math;

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/providers.dart';
import '../auth/auth_controller.dart';

const pcControlChannel = MethodChannel('ai.dhanz/pc_control');

class ApprovalPanelSignal extends Notifier<int> {
  @override
  int build() => 0;
  void open() => state++;
}

final approvalPanelSignalProvider = NotifierProvider<ApprovalPanelSignal, int>(ApprovalPanelSignal.new);

class ChatApprovalPanel extends ConsumerWidget {
  const ChatApprovalPanel({super.key});
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    if (kIsWeb || defaultTargetPlatform != TargetPlatform.windows) return const SizedBox.shrink();
    return _FloatingApprovals(key: ValueKey(ref.watch(authControllerProvider.select((s) => s.value?.id))));
  }
}

class _FloatingApprovals extends ConsumerStatefulWidget {
  const _FloatingApprovals({super.key});
  @override
  ConsumerState<_FloatingApprovals> createState() => _FloatingApprovalsState();
}

class _FloatingApprovalsState extends ConsumerState<_FloatingApprovals> {
  final _page = GlobalKey<_ActionsPageState>();
  int _pending = 0;

  void _changed(List<Map<String, dynamic>> actions) {
    if (mounted) {
      setState(() => _pending = actions.where((a) => a['provider'] == 'windows' && a['status'] == 'pending').length);
    }
  }

  @override
  Widget build(BuildContext context) {
    ref.listen(approvalPanelSignalProvider, (_, _) => _page.currentState?._load());
    return LayoutBuilder(
      builder: (context, constraints) => Stack(
        children: [
          Positioned(
            right: 12,
            top: 12,
            width: math.min(400.0, math.max(0.0, constraints.maxWidth - 24)),
            child: Offstage(
              offstage: _pending == 0,
              child: SizedBox(
                height: math.min(300.0, math.max(0.0, constraints.maxHeight - 24)),
                child: _ActionsPage(key: _page, floating: true, onActions: _changed),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class AutomationScreen extends ConsumerWidget {
  const AutomationScreen({super.key});
  @override
  Widget build(BuildContext context, WidgetRef ref) =>
      _ActionsPage(key: ValueKey(ref.watch(authControllerProvider.select((s) => s.value?.id))));
}

class _ActionsPage extends ConsumerStatefulWidget {
  const _ActionsPage({super.key, this.floating = false, this.onActions});
  final bool floating;
  final ValueChanged<List<Map<String, dynamic>>>? onActions;
  @override
  ConsumerState<_ActionsPage> createState() => _ActionsPageState();
}

class _ActionsPageState extends ConsumerState<_ActionsPage> {
  List<Map<String, dynamic>> _actions = [];
  bool _pcEnabled = false;
  bool _busy = false;
  String? _error;
  List<Map<String, dynamic>> _windowsList = [];
  int? _targetId;
  Uint8List? _capture;
  static const _windowOperations = {'click', 'type_text', 'press_key', 'scroll', 'capture_window'};

  Future<void> _refreshWindows() async {
    try {
      final windows = await pcControlChannel.invokeListMethod<dynamic>('listWindows', {});
      if (mounted) {
        setState(() {
          _windowsList = (windows ?? []).map((w) => Map<String, dynamic>.from(w as Map)).toList();
          _targetId = null;
          _capture = null;
        });
      }
    } catch (e) {
      if (mounted) setState(() => _error = 'Cannot list supported windows: $e');
    }
  }

  Future<void> _selectTarget(int? id) async {
    if (id == null) return;
    try {
      await pcControlChannel.invokeMethod('selectTarget', {'window_id': id});
      if (mounted) {
        setState(() {
          _targetId = id;
          _capture = null;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _targetId = null;
          _error = '$e';
        });
      }
    }
  }

  Timer? _timer;
  bool get _windows => !kIsWeb && defaultTargetPlatform == TargetPlatform.windows;

  @override
  void initState() {
    super.initState();
    Future.microtask(_load);
    _timer = Timer.periodic(const Duration(seconds: 10), (_) {
      if (!_busy) _load();
    });
  }

  @override
  void dispose() {
    _timer?.cancel();
    if (_windows) unawaited(pcControlChannel.invokeMethod('setEnabled', {'enabled': false}));
    super.dispose();
  }

  Future<void> _load() async {
    try {
      final data = await ref.read(apiClientProvider).automationActions();
      if (mounted) {
        setState(() {
          _actions = (data['actions'] as List).cast<Map<String, dynamic>>();
          _error = null;
        });
        widget.onActions?.call(_actions);
      }
    } catch (e) {
      if (mounted) setState(() => _error = e.toString());
    }
  }

  Future<void> _setPc(bool enabled) async {
    try {
      final active = await pcControlChannel.invokeMethod<bool>('setEnabled', {'enabled': enabled}) ?? false;
      if (mounted) {
        setState(() {
          _pcEnabled = active;
          _targetId = null;
          _capture = null;
        });
      }
    } catch (_) {
      if (mounted) setState(() => _error = 'PC control is unavailable in this app build.');
    }
  }

  Future<void> _handle(Map<String, dynamic> action, bool approve) async {
    if (_busy) return;
    final windows = action['provider'] == 'windows';
    final windowAction = windows && _windowOperations.contains((action['payload'] as Map)['operation']);
    if (approve && windows && widget.floating && !_pcEnabled) await _setPc(true);
    if (!mounted) return;
    if (approve && windows && (!_windows || !_pcEnabled)) return;
    if (approve && windowAction && _targetId == null && widget.floating) {
      await _refreshWindows();
      if (!mounted) return;
      final selected = await showDialog<int>(
        context: context,
        builder: (context) => SimpleDialog(
          title: const Text('Choose the target window'),
          children: [
            for (final window in _windowsList)
              SimpleDialogOption(
                onPressed: () => Navigator.pop(context, window['id'] as int),
                child: Text(window['title'] as String),
              ),
          ],
        ),
      );
      if (selected == null || !mounted) return;
      await _selectTarget(selected);
    }
    if (!mounted) return;
    if (approve && windowAction && _targetId == null) {
      setState(() => _error = 'Refresh windows and select a target before approving this action.');
      return;
    }
    if (approve && !widget.floating) {
      final accepted = await showDialog<bool>(
        context: context,
        builder: (context) => AlertDialog(
          title: Text(windows ? 'Review PC action' : 'Approve GitHub change?'),
          content: SizedBox(
            width: 600,
            child: SingleChildScrollView(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: [
                  if (!windows)
                    const Text('This changes GitHub and may trigger CI. Review the exact content and destination.'),
                  SelectableText(const JsonEncoder.withIndent('  ').convert(action['payload'])),
                  if (windowAction) Text('Target: ${_windowsList.firstWhere((w) => w['id'] == _targetId)['title']}'),
                ],
              ),
            ),
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
            FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Approve this action')),
          ],
        ),
      );
      if (accepted != true || !mounted || (windows && !_pcEnabled)) return;
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final api = ref.read(apiClientProvider);
      if (!approve) {
        await api.handleAction(action['id'] as String, 'reject');
      } else if (windows) {
        final claimed = await api.handleAction(action['id'] as String, 'windows-claim');
        bool success = false;
        try {
          if (mounted && _pcEnabled) {
            final outcome = await pcControlChannel.invokeMethod<dynamic>('execute', claimed['payload']);
            success = outcome == true || outcome is Uint8List;
            if (outcome is Uint8List && mounted) setState(() => _capture = outcome);
          }
        } finally {
          await api.handleAction(action['id'] as String, 'windows-result', body: {'success': success});
        }
      } else {
        await api.handleAction(action['id'] as String, 'approve');
      }
      if (mounted) await _load();
    } catch (e) {
      if (mounted) setState(() => _error = '$e Check the action status before retrying.');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  String _summary(Map<String, dynamic> action) {
    final payload = action['payload'] as Map;
    final operation = payload['operation'];
    const apps = {
      'chrome': 'Google Chrome',
      'notepad': 'Notepad',
      'calculator': 'Calculator',
      'file_explorer': 'File Explorer',
    };
    if (operation == 'open_app') return 'Open ${apps[payload['app']] ?? payload['app']}?';
    if (operation == 'open_url') return 'Open ${payload['url']}?';
    if (operation == 'type_text') return 'Type: ${payload['text']}';
    if (operation == 'press_key') return 'Press ${payload['key']}?';
    if (operation == 'click') return 'Click at ${payload['x']}, ${payload['y']}?';
    if (operation == 'scroll') return 'Scroll ${payload['scroll_delta']}?';
    return 'Capture the selected window?';
  }

  Widget _floatingBody() => Material(
    elevation: 12,
    borderRadius: BorderRadius.circular(16),
    clipBehavior: Clip.antiAlias,
    child: ListView(
      shrinkWrap: true,
      padding: const EdgeInsets.all(12),
      children: [
        if (_error != null) Text(_error!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
        for (final action in _actions.where((a) => a['provider'] == 'windows' && a['status'] == 'pending'))
          Padding(
            padding: const EdgeInsets.only(bottom: 8),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(_summary(action), maxLines: 3, overflow: TextOverflow.ellipsis),
                const SizedBox(height: 8),
                Row(
                  children: [
                    FilledButton(onPressed: _busy ? null : () => _handle(action, true), child: const Text('Approve')),
                    const SizedBox(width: 8),
                    TextButton(onPressed: _busy ? null : () => _handle(action, false), child: const Text('Decline')),
                  ],
                ),
              ],
            ),
          ),
      ],
    ),
  );

  @override
  Widget build(BuildContext context) => widget.floating
      ? _floatingBody()
      : Scaffold(
          appBar: AppBar(
            title: Text(widget.floating ? 'Review actions' : 'Actions and PC control'),
            automaticallyImplyLeading: false,
            leading: widget.floating
                ? null
                : IconButton(icon: const Icon(Icons.arrow_back), onPressed: () => context.go('/settings')),
            actions: [
              IconButton(tooltip: 'Refresh actions', onPressed: _busy ? null : _load, icon: const Icon(Icons.refresh)),
            ],
          ),
          body: ListView(
            padding: const EdgeInsets.all(16),
            children: [
              if (!widget.floating) ...[
                const Text(
                  'Ask Dhanz to prepare a GitHub change or open an app or HTTPS page. Review each request here.',
                ),
                const SizedBox(height: 12),
                ListTile(
                  leading: const Icon(Icons.code),
                  title: const Text('GitHub connection'),
                  subtitle: const Text(
                    'Writes need a selected-repository token with Contents, Issues and Pull requests write permissions.',
                  ),
                  trailing: TextButton(onPressed: () => context.go('/github'), child: const Text('Manage')),
                ),
              ],
              if (_windows)
                SwitchListTile(
                  title: Text(_pcEnabled ? 'PC control enabled — this PC' : 'PC control is off'),
                  subtitle: Text(
                    widget.floating
                        ? 'Approve each action on this PC. Minimize to keep the session active.'
                        : 'Allows app launches, selected-window mouse/keyboard actions and local captures after approval. '
                              'Leaving chat or this screen switches control off. Minimizing the chat panel keeps this session active.',
                  ),
                  value: _pcEnabled,
                  onChanged: _busy ? null : _setPc,
                ),
              if (_pcEnabled)
                OutlinedButton(
                  onPressed: _busy ? null : _refreshWindows,
                  child: const Text('Refresh supported windows'),
                ),
              if (_pcEnabled && _windowsList.isNotEmpty)
                DropdownButtonFormField<int>(
                  key: ValueKey(_windowsList),
                  initialValue: _targetId,
                  decoration: const InputDecoration(labelText: 'Target window for mouse, keyboard and capture'),
                  isExpanded: true,
                  items: [
                    for (final window in _windowsList)
                      DropdownMenuItem(
                        value: window['id'] as int,
                        child: Text(window['title'] as String, overflow: TextOverflow.ellipsis),
                      ),
                  ],
                  onChanged: _busy ? null : _selectTarget,
                ),
              if (_capture != null) ...[
                const Text(
                  'Local window capture — not sent to the AI. Attach a screenshot in chat if you want image analysis.',
                ),
                SizedBox(height: 320, child: Image.memory(_capture!, fit: BoxFit.contain)),
                TextButton(onPressed: () => setState(() => _capture = null), child: const Text('Clear capture')),
              ],
              if (_pcEnabled)
                FilledButton.icon(
                  onPressed: () => _setPc(false),
                  icon: const Icon(Icons.stop_circle),
                  label: const Text('Stop control'),
                ),
              if (!_windows) const Text('Approve PC actions in the DHANZ Windows app on the PC you want to control.'),
              if (_error != null) Text(_error!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
              if (_actions.isEmpty) const Padding(padding: EdgeInsets.all(24), child: Text('No action requests yet.')),
              for (final action in _actions)
                Card(
                  child: Padding(
                    padding: const EdgeInsets.all(12),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          '${action['provider']}: ${(action['payload'] as Map)['operation']}',
                          style: Theme.of(context).textTheme.titleMedium,
                        ),
                        Text('Status: ${action['status']} · Expires: ${action['expires_at']}'),
                        SelectableText(const JsonEncoder.withIndent('  ').convert(action['payload'])),
                        if (action['result'] != null)
                          SelectableText(const JsonEncoder.withIndent('  ').convert(action['result'])),
                        if (action['status'] == 'pending')
                          Wrap(
                            spacing: 8,
                            children: [
                              FilledButton(
                                onPressed: _busy || (action['provider'] == 'windows' && (!_windows || !_pcEnabled))
                                    ? null
                                    : () => _handle(action, true),
                                child: const Text('Review and approve'),
                              ),
                              TextButton(
                                onPressed: _busy ? null : () => _handle(action, false),
                                child: const Text('Reject'),
                              ),
                            ],
                          ),
                      ],
                    ),
                  ),
                ),
            ],
          ),
        );
}
