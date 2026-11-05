import 'dart:async';

import 'package:dhanz_ai/core/api/api_client.dart';
import 'package:dhanz_ai/core/platform/web_runtime.dart';
import 'package:dhanz_ai/core/platform/web_updates.dart';
import 'package:dhanz_ai/core/providers.dart';
import 'package:dhanz_ai/core/storage/secure_store.dart';
import 'package:dhanz_ai/core/uploads/upload_queue.dart';
import 'package:dhanz_ai/features/auth/auth_controller.dart';
import 'package:dhanz_ai/models/models.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

class UpdateAuth extends AuthController {
  @override
  Future<User?> build() async => const User(
    id: 'owner',
    email: 'owner@example.test',
    displayName: 'Owner',
    role: 'user',
    routingPolicy: 'balanced',
  );
}

class UpdateApi extends ApiClient {
  UpdateApi()
    : super(store: MemorySecureStore(), baseUrl: 'https://example.test');
  int checks = 0, starts = 0;
  bool authorizedHost = true;
  String outcome = 'completed';
  Completer<Map<String, dynamic>>? waiting;
  final keys = <String>[];
  @override
  Future<Map<String, dynamic>> webUpdateCheck() async {
    checks++;
    return {
      'release': {'version': '0.10.0', 'build': 28},
      'servers': authorizedHost
          ? [
              {'id': 'owned-server', 'name': 'AWS', 'online': true},
            ]
          : [],
    };
  }

  @override
  Future<Map<String, dynamic>> webUpdateStart(
    String serverId,
    String key,
  ) async {
    starts++;
    keys.add(key);
    return {'id': 'job', 'status': 'queued'};
  }

  @override
  Future<Map<String, dynamic>> webUpdateStatus(String id) async =>
      waiting == null ? {'id': id, 'status': outcome} : waiting!.future;
}

class Runtime extends WebUpdateRuntime {
  WebBuild served = (version: '0.9.9', build: 27);
  int refreshes = 0;
  @override
  Future<WebBuild> servedBuild() async => served;
  @override
  Future<void> refresh(WebBuild minimum) async {
    refreshes++;
  }
}

class BusyUploads extends UploadQueue {
  @override
  List<UploadEntry> build() => const [
    UploadEntry(
      id: 1,
      name: 'active.pdf',
      status: UploadStatus.uploading,
      size: 10,
    ),
  ];
}

Future<ProviderContainer> setup(
  UpdateApi api,
  Runtime runtime, {
  bool uploads = false,
}) async {
  final container = ProviderContainer(
    overrides: [
      authControllerProvider.overrideWith(UpdateAuth.new),
      apiClientProvider.overrideWithValue(api),
      webUpdateRuntimeProvider.overrideWithValue(runtime),
      runningWebBuildProvider.overrideWithValue((version: '0.9.9', build: 27)),
      webUpdatePollDelayProvider.overrideWithValue(Duration.zero),
      if (uploads) uploadQueueProvider.overrideWith(BusyUploads.new),
    ],
  );
  await container.read(authControllerProvider.future);
  container.read(webUpdateControllerProvider);
  await Future<void>.microtask(() {});
  await Future<void>.microtask(() {});
  return container;
}

void main() {
  test(
    'manual update checks GitHub fresh, queues one owned task then refreshes',
    () async {
      final api = UpdateApi(), runtime = Runtime();
      final container = await setup(api, runtime);
      addTearDown(container.dispose);
      final controller = container.read(webUpdateControllerProvider.notifier);
      final first = controller.update();
      final doubleTap = controller.update();
      await Future.wait([first, doubleTap]);
      expect(api.checks, 2); // startup plus explicit fresh check
      expect(api.starts, 1);
      expect(runtime.refreshes, 1);
      expect(api.keys.single.length, 32);
    },
  );
  test('a known failed task permits a fresh explicit retry without automatic replay', () async {
    final api = UpdateApi()..outcome = 'failed';
    final runtime = Runtime();
    final container = await setup(api, runtime);
    addTearDown(container.dispose);
    final controller = container.read(webUpdateControllerProvider.notifier);
    await controller.update();
    expect(api.starts, 1);
    expect(runtime.refreshes, 0);
    api.outcome = 'completed';
    await controller.update();
    expect(api.starts, 2);
    expect(api.keys[0], isNot(api.keys[1]));
    expect(runtime.refreshes, 1);
  });
  test('an uncertain task retains its request key instead of creating a new server action', () async {
    final api = UpdateApi()..outcome = 'uncertain';
    final runtime = Runtime();
    final container = await setup(api, runtime);
    addTearDown(container.dispose);
    final controller = container.read(webUpdateControllerProvider.notifier);
    await controller.update();
    await controller.update();
    expect(api.keys.length, 2);
    expect(api.keys[0], api.keys[1]); // backend returns the same durable job for this key
    expect(runtime.refreshes, 0);
  });
  test(
    'regular user can refresh an already deployed build without a host task',
    () async {
      final api = UpdateApi()..authorizedHost = false;
      final runtime = Runtime()..served = (version: '0.10.0', build: 28);
      final container = await setup(api, runtime);
      addTearDown(container.dispose);
      await container.read(webUpdateControllerProvider.notifier).update();
      expect(api.starts, 0);
      expect(runtime.refreshes, 1);
    },
  );
  test(
    'regular user cannot deploy a GitHub build without a paired update host',
    () async {
      final api = UpdateApi()..authorizedHost = false, runtime = Runtime();
      final container = await setup(api, runtime);
      addTearDown(container.dispose);
      await container.read(webUpdateControllerProvider.notifier).update();
      expect(api.starts, 0);
      expect(runtime.refreshes, 0);
      expect(
        container.read(webUpdateControllerProvider).error,
        contains('server owner'),
      );
    },
  );
  test(
    'uploads prevent cache refresh and no server action is queued',
    () async {
      final api = UpdateApi(), runtime = Runtime();
      final container = await setup(api, runtime, uploads: true);
      addTearDown(container.dispose);
      await container.read(webUpdateControllerProvider.notifier).update();
      expect(api.starts, 0);
      expect(runtime.refreshes, 0);
      expect(
        container.read(webUpdateControllerProvider).error,
        contains('uploads'),
      );
    },
  );
  testWidgets(
    'Update button is available even before a newer version is detected',
    (tester) async {
      final api = UpdateApi(), runtime = Runtime();
      final container = await setup(api, runtime);
      addTearDown(container.dispose);
      await tester.pumpWidget(
        UncontrolledProviderScope(
          container: container,
          child: const MaterialApp(home: Scaffold(body: WebUpdateTile())),
        ),
      );
      await tester.pump();
      expect(find.widgetWithText(FilledButton, 'Update'), findsOneWidget);
    },
  );
  test('semver and build comparison does not mistake 0.10 for 0.9', () {
    expect(
      compareWebBuilds(
        (version: '0.10.0', build: 28),
        (version: '0.9.9', build: 99),
      ),
      greaterThan(0),
    );
    expect(
      compareWebBuilds(
        (version: '0.10.0', build: 29),
        (version: '0.10.0', build: 28),
      ),
      greaterThan(0),
    );
  });
}
