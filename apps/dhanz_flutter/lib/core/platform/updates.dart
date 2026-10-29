import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:http/http.dart' as http;
import 'package:url_launcher/url_launcher.dart';

import '../../models/models.dart';
import '../providers.dart';
import 'app_version.dart';
import 'installer_stub.dart' if (dart.library.io) 'installer_io.dart' as installer;

/// The platform name used by the update manifest, or null where updates come from elsewhere (web).
final updatePlatformProvider = Provider<String?>((ref) {
  if (kIsWeb) return null;
  return switch (defaultTargetPlatform) {
    TargetPlatform.windows => 'windows',
    TargetPlatform.macOS => 'macos',
    TargetPlatform.android => 'android',
    TargetPlatform.iOS => 'ios',
    _ => null,
  };
});

class UpdateState {
  const UpdateState({this.info, this.dismissed = false, this.progress, this.error});

  final UpdateInfo? info;
  final bool dismissed;

  /// Download progress 0..1 while installing.
  final double? progress;
  final String? error;

  bool get showBanner => info != null && info!.updateAvailable && (!dismissed || info!.mandatory);
}

/// Checks the server for a newer app version once per start.
class UpdateController extends Notifier<UpdateState> {
  @override
  UpdateState build() {
    unawaited(check());
    return const UpdateState();
  }

  Future<void> check() async {
    final platform = ref.read(updatePlatformProvider);
    if (platform == null) return;
    try {
      final version = await ref.read(appVersionProvider.future);
      final info = await ref.read(apiClientProvider).checkForUpdate(platform, version);
      if (ref.mounted) state = UpdateState(info: info);
    } on Object catch (e) {
      debugPrint('Update check failed: $e');
    }
  }

  void dismiss() => state = UpdateState(info: state.info, dismissed: true);

  Future<void> install() async {
    final info = state.info;
    final url = info?.url == null ? null : Uri.tryParse(info!.url!);
    if (info == null || url == null) return;
    // Windows: download, verify and run the installer. Elsewhere the store / download page handles it.
    if (ref.read(updatePlatformProvider) == 'windows' && info.sha256 != null) {
      state = UpdateState(info: info, progress: 0);
      final client = http.Client();
      try {
        await installer.installWindowsUpdate(
          url,
          info.sha256!,
          client: client,
          onProgress: (p) => state = UpdateState(info: info, progress: p),
        );
      } on Object catch (e) {
        state = UpdateState(info: info, error: 'The update could not be installed: $e');
      } finally {
        client.close();
      }
      return;
    }
    if (!await launchUrl(url, mode: LaunchMode.externalApplication)) {
      state = UpdateState(info: info, error: 'Could not open $url');
    }
  }
}

final updateControllerProvider = NotifierProvider<UpdateController, UpdateState>(UpdateController.new);

/// Shown above every screen when a newer version is available.
class UpdateBanner extends ConsumerWidget {
  const UpdateBanner({required this.child, super.key});

  final Widget child;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final update = ref.watch(updateControllerProvider);
    if (!update.showBanner) return child;
    final info = update.info!;
    final controller = ref.read(updateControllerProvider.notifier);
    final installing = update.progress != null;
    return Column(
      children: [
        Material(
          child: SafeArea(
            bottom: false,
            child: MaterialBanner(
              leading: const Icon(Icons.system_update_alt),
              content: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(
                    info.mandatory
                        ? 'DHANZ AI ${info.latestVersion} is required to keep using this server.'
                        : 'DHANZ AI ${info.latestVersion} is available.',
                  ),
                  if (info.notes != null) Text(info.notes!, maxLines: 2, overflow: TextOverflow.ellipsis),
                  if (installing) ...[const SizedBox(height: 8), LinearProgressIndicator(value: update.progress)],
                  if (update.error != null)
                    Text(update.error!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
                ],
              ),
              actions: [
                if (!info.mandatory)
                  TextButton(onPressed: installing ? null : controller.dismiss, child: const Text('Later')),
                FilledButton(onPressed: installing ? null : controller.install, child: const Text('Update')),
              ],
            ),
          ),
        ),
        Expanded(
          child: MediaQuery.removePadding(context: context, removeTop: true, child: child),
        ),
      ],
    );
  }
}
