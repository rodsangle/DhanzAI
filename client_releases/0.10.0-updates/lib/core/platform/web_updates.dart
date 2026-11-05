import 'dart:async';
import 'dart:math';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../features/auth/auth_controller.dart';
import '../providers.dart';
import '../uploads/upload_queue.dart';
import 'web_runtime.dart';

final webUpdateRuntimeProvider = Provider<WebUpdateRuntime>(
  (ref) => createWebUpdateRuntime(),
);
final runningWebBuildProvider = Provider<WebBuild>(
  (ref) => (version: runningWebVersion, build: runningWebBuild),
);
final webUpdatePollDelayProvider = Provider<Duration>(
  (ref) => const Duration(seconds: 2),
);

class WebUpdateState {
  const WebUpdateState({
    this.info,
    this.busy = false,
    this.message,
    this.error,
  });
  final Map<String, dynamic>? info;
  final bool busy;
  final String? message;
  final String? error;
  WebBuild? get latest {
    final release = info?['release'] as Map<String, dynamic>?;
    return release == null
        ? null
        : (
            version: release['version'] as String,
            build: release['build'] as int,
          );
  }

  List<Map<String, dynamic>> get servers =>
      ((info?['servers'] as List<dynamic>?) ?? []).cast<Map<String, dynamic>>();
}

class WebUpdateController extends Notifier<WebUpdateState> {
  int _epoch = 0;
  String? _owner;
  String _server = '';
  String? _requestKey;
  String? _requestedBuild;
  int? _busyEpoch;
  @override
  WebUpdateState build() {
    _owner = ref.watch(
      authControllerProvider.select((value) => value.value?.id),
    );
    ref.watch(connectionRevisionProvider);
    _server = ref.watch(apiClientProvider).baseUrl;
    final epoch = ++_epoch;
    _requestKey = null;
    ref.onDispose(() => _epoch++);
    if (_owner != null) {
      Future.microtask(() {
        if (_current(epoch)) unawaited(check());
      });
    }
    return const WebUpdateState();
  }

  bool _current(int epoch) =>
      ref.mounted &&
      epoch == _epoch &&
      _owner != null &&
      ref.read(authControllerProvider).value?.id == _owner &&
      ref.read(apiClientProvider).baseUrl == _server;
  bool get _uploadsBusy => ref.read(uploadQueueProvider).any((job) => job.busy);

  Future<void> check() async {
    final epoch = _epoch;
    if (!_current(epoch) || _busyEpoch == epoch) return;
    _busyEpoch = epoch;
    state = WebUpdateState(
      info: state.info,
      busy: true,
      message: 'Checking GitHub…',
    );
    try {
      final info = await ref.read(apiClientProvider).webUpdateCheck();
      if (_current(epoch)) {
        state = WebUpdateState(
          info: info,
          message: 'GitHub web release checked.',
        );
      }
    } catch (error) {
      if (_current(epoch)) {
        state = WebUpdateState(info: state.info, error: '$error');
      }
    } finally {
      if (_busyEpoch == epoch) _busyEpoch = null;
    }
  }

  Future<void> update({String? serverId}) async {
    final epoch = _epoch;
    if (!_current(epoch) || _busyEpoch == epoch) return;
    if (_uploadsBusy) {
      state = WebUpdateState(
        info: state.info,
        error: 'Finish or cancel pending uploads before updating.',
      );
      return;
    }
    _busyEpoch = epoch;
    state = WebUpdateState(
      info: state.info,
      busy: true,
      message: 'Checking the latest GitHub build…',
    );
    try {
      final api = ref.read(apiClientProvider);
      final info = await api.webUpdateCheck();
      if (!_current(epoch)) return;
      state = WebUpdateState(
        info: info,
        busy: true,
        message: 'Checking the served app…',
      );
      final target = state.latest!;
      final buildKey = '${target.version}+${target.build}';
      if (_requestedBuild != buildKey) {
        _requestKey = null;
        _requestedBuild = buildKey;
      }
      final runtime = ref.read(webUpdateRuntimeProvider);
      final served = await runtime.servedBuild();
      if (!_current(epoch)) return;
      if (compareWebBuilds(served, target) < 0) {
        final hosts = state.servers
            .where((host) => serverId == null || host['id'] == serverId)
            .toList();
        if (hosts.length != 1) {
          throw StateError(
            hosts.isEmpty
                ? 'The latest build needs a server update. The server owner must enable the web-update recipe.'
                : 'Choose your update server on the App update page.',
          );
        }
        if (hosts.single['online'] != true) {
          throw StateError(
            'The update companion is offline. No update was queued.',
          );
        }
        _requestKey ??= List.generate(
          32,
          (_) => Random.secure().nextInt(16).toRadixString(16),
        ).join();
        var job = await api.webUpdateStart(
          hosts.single['id'] as String,
          _requestKey!,
        );
        for (var attempt = 0; attempt < 150; attempt++) {
          if (!_current(epoch)) return;
          final status = job['status'];
          if (status == 'completed') break;
          if (!const ['queued', 'executing'].contains(status)) {
            throw StateError(
              'Web update $status. Check Connected operations before retrying.',
            );
          }
          state = WebUpdateState(
            info: info,
            busy: true,
            message: status == 'queued'
                ? 'Update queued on your server…'
                : 'Server is downloading and installing the GitHub build…',
          );
          await Future<void>.delayed(ref.read(webUpdatePollDelayProvider));
          if (!_current(epoch)) return;
          job = await api.webUpdateStatus(job['id'] as String);
        }
        if (job['status'] != 'completed') {
          throw StateError(
            'The update is still running. Check Activity, then press Update again.',
          );
        }
      }
      if (!_current(epoch)) return;
      if (_uploadsBusy) {
        throw StateError(
          'Server update finished. Complete your new uploads, then press Update to refresh.',
        );
      }
      state = WebUpdateState(
        info: info,
        busy: true,
        message:
            'Refreshing cached app files… Save unsent text before updating.',
      );
      await runtime.refresh(target);
      if (_current(epoch)) {
        state = WebUpdateState(info: info, message: 'App refresh requested.');
      }
    } catch (error) {
      if (_current(epoch)) {
        state = WebUpdateState(info: state.info, error: '$error');
      }
    } finally {
      if (_busyEpoch == epoch) _busyEpoch = null;
    }
  }
}

final webUpdateControllerProvider =
    NotifierProvider<WebUpdateController, WebUpdateState>(
      WebUpdateController.new,
    );

class WebUpdateTile extends ConsumerWidget {
  const WebUpdateTile({super.key});
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final state = ref.watch(webUpdateControllerProvider);
    final current = ref.watch(runningWebBuildProvider);
    return ListTile(
      leading: const Icon(Icons.system_update_alt),
      title: Text('App version ${current.version}'),
      subtitle: Text(
        '${state.error ?? state.message ?? 'Checks the latest GitHub web release.'}\nReloads this app; save unsent text first.',
      ),
      trailing: FilledButton(
        onPressed: state.busy
            ? null
            : () => ref.read(webUpdateControllerProvider.notifier).update(),
        child: Text(state.busy ? 'Updating…' : 'Update'),
      ),
      onTap: () => context.push('/updates'),
    );
  }
}

class WebUpdatesScreen extends ConsumerWidget {
  const WebUpdatesScreen({super.key});
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final state = ref.watch(webUpdateControllerProvider);
    final current = ref.watch(runningWebBuildProvider);
    final controller = ref.read(webUpdateControllerProvider.notifier);
    return Scaffold(
      appBar: AppBar(title: const Text('App update')),
      body: ListView(
        padding: const EdgeInsets.all(20),
        children: [
          Text('Installed ${current.version} (${current.build})'),
          if (state.latest != null)
            Text(
              'Latest GitHub web build: ${state.latest!.version} (${state.latest!.build})',
            ),
          const Text(
            'Update installs a newer GitHub web build on your authorized server when needed, then refreshes this phone/browser app. Save unsent text first. Active uploads must finish before refresh. Sign-in data is kept.',
          ),
          if (state.busy) const LinearProgressIndicator(),
          if (state.message != null) Text(state.message!),
          if (state.error != null) SelectableText(state.error!),
          FilledButton(
            onPressed: state.busy ? null : () => controller.update(),
            child: const Text('Update now'),
          ),
          TextButton(
            onPressed: state.busy ? null : controller.check,
            child: const Text('Check GitHub again'),
          ),
          if (state.servers.length > 1)
            for (final server in state.servers)
              OutlinedButton(
                onPressed: state.busy
                    ? null
                    : () => controller.update(serverId: server['id'] as String),
                child: Text('Update with ${server['name']}'),
              ),
        ],
      ),
    );
  }
}
