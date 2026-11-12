import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api/api_client.dart';
import '../../core/providers.dart';
import '../auth/auth_controller.dart';

class CreativeActivityState {
  const CreativeActivityState({this.jobs = const [], this.notice});
  final List<Map<String, dynamic>> jobs;
  final String? notice;
  int get activeCount => jobs.where((j) => const ['queued', 'processing'].contains(j['status'])).length;
}

/// Account-scoped job tracking lives at the app root, independently of the open chat/Studio route.
class CreativeActivity extends Notifier<CreativeActivityState> {
  static Duration interval = const Duration(seconds: 5);
  Timer? _timer;
  String? _owner;
  int _epoch = 0;
  bool _busy = false;
  bool _initialized = false;
  final Map<String, String> _known = {};
  DateTime _startedAt = DateTime.now();

  @override
  CreativeActivityState build() {
    _timer?.cancel();
    final epoch = ++_epoch;
    _owner = ref.watch(authControllerProvider.select((s) => s.value?.id));
    _known.clear();
    _initialized = false;
    _startedAt = DateTime.now();
    _busy = false;
    ref.onDispose(() {
      _timer?.cancel();
      _epoch++;
    });
    if (_owner != null) {
      _timer = Timer.periodic(interval, (_) {
        if (epoch == _epoch) unawaited(refresh());
      });
      unawaited(
        Future<void>.microtask(() async {
          if (epoch == _epoch) await refresh();
        }),
      );
    }
    return const CreativeActivityState();
  }

  void track(Map<String, dynamic> job, String? owner) {
    if (!ref.mounted || owner == null || owner != _owner || job['id'] is! String) return;
    final jobs = {for (final item in state.jobs) item['id'] as String: item, job['id'] as String: job};
    _known[job['id'] as String] = job['status'] as String;
    state = CreativeActivityState(jobs: jobs.values.toList(), notice: state.notice);
  }

  void dismiss() => state = CreativeActivityState(jobs: state.jobs);

  Future<void> refresh() async {
    if (_owner == null || _busy) return;
    _busy = true;
    final epoch = _epoch;
    final previous = Map<String, String>.from(_known);
    try {
      final api = ref.read(apiClientProvider);
      final page = await api.creations();
      if (epoch != _epoch) return;
      final jobs = {for (final j in page) j['id'] as String: j};
      // An older long-running video can fall off the latest gallery page. Keep following its ID.
      for (final entry in previous.entries) {
        if (const ['queued', 'processing'].contains(entry.value) && !jobs.containsKey(entry.key)) {
          try {
            jobs[entry.key] = await api.creation(entry.key);
          } on ApiException catch (e) {
            if (e.statusCode != 404) rethrow;
          }
        }
      }
      if (epoch != _epoch) return;
      String? notice = state.notice;
      for (final job in jobs.values) {
        final id = job['id'] as String;
        final before = previous[id];
        final after = job['status'] as String;
        final created = DateTime.tryParse(job['created_at'] as String? ?? '');
        final newSinceStart = _initialized && before == null && created != null && !created.isBefore(_startedAt);
        if ((before == 'queued' || before == 'processing' || newSinceStart) && before != after) {
          if (after == 'completed') notice = 'Your ${job['kind']} is ready in Creative Studio.';
          if (after == 'failed') notice = '${job['kind']} generation failed. Open Creative Studio for details.';
        }
      }
      _known
        ..clear()
        ..addAll({for (final j in jobs.values) j['id'] as String: j['status'] as String});
      _initialized = true;
      state = CreativeActivityState(jobs: jobs.values.toList(), notice: notice);
    } on ApiException {
      // A temporary connection failure never cancels a server job.
    } finally {
      if (epoch == _epoch) _busy = false;
    }
  }
}

final creativeActivityProvider = NotifierProvider<CreativeActivity, CreativeActivityState>(CreativeActivity.new);

class CreativeActivityShell extends ConsumerWidget {
  const CreativeActivityShell({required this.child, required this.onOpen, super.key});
  final Widget child;
  final VoidCallback onOpen;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final activity = ref.watch(creativeActivityProvider);
    if (activity.activeCount == 0 && activity.notice == null) return child;
    return Column(
      children: [
        Expanded(child: child),
        Material(
          child: SafeArea(
            top: false,
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
              child: Row(
                children: [
                  if (activity.activeCount > 0)
                    const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2)),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Text(
                      activity.notice ??
                          '${activity.activeCount} creation(s) generating in the background. You can switch chats.',
                    ),
                  ),
                  TextButton(onPressed: onOpen, child: const Text('Open Studio')),
                  if (activity.notice != null)
                    IconButton(
                      onPressed: ref.read(creativeActivityProvider.notifier).dismiss,
                      icon: const Icon(Icons.close),
                      tooltip: 'Dismiss',
                    ),
                ],
              ),
            ),
          ),
        ),
      ],
    );
  }
}
