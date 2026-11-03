import 'dart:async';

import 'package:dhanz_ai/core/api/api_client.dart';
import 'package:dhanz_ai/core/providers.dart';
import 'package:dhanz_ai/core/storage/secure_store.dart';
import 'package:dhanz_ai/features/auth/auth_controller.dart';
import 'package:dhanz_ai/features/chat/chat_controller.dart';
import 'package:dhanz_ai/features/creative/creative_activity.dart';
import 'package:dhanz_ai/models/models.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

const user = User(
  id: 'owner',
  email: 'owner@example.com',
  displayName: 'Owner',
  role: 'user',
  routingPolicy: 'balanced',
);

class ActivityAuth extends AuthController {
  @override
  Future<User?> build() async => user;
  void signOut() => state = const AsyncData(null);
}

class ActivityApi extends ApiClient {
  ActivityApi() : super(store: MemorySecureStore(), baseUrl: 'https://example.com');
  List<Map<String, dynamic>> jobs = [];
  final details = <String, Map<String, dynamic>>{};
  final detailRequests = <String>[];
  int cancels = 0;
  bool offline = false;
  Completer<List<Map<String, dynamic>>>? pending;

  @override
  Future<List<Map<String, dynamic>>> creations({int offset = 0}) async {
    if (offline) throw ApiException(0, 'Offline');
    if (pending != null) return pending!.future;
    return jobs.map((j) => Map<String, dynamic>.from(j)).toList();
  }

  @override
  Future<Map<String, dynamic>> creation(String id) async {
    detailRequests.add(id);
    return details[id]!;
  }

  @override
  Future<void> cancelCreation(String id) async {
    cancels++;
  }
}

Map<String, dynamic> job(String status, {String id = 'job-1', String kind = 'image'}) => {
  'id': id,
  'status': status,
  'kind': kind,
  'created_at': DateTime.now().toUtc().toIso8601String(),
};

Future<ProviderContainer> setup(ActivityApi api) async {
  final container = ProviderContainer(
    overrides: [apiClientProvider.overrideWithValue(api), authControllerProvider.overrideWith(ActivityAuth.new)],
  );
  addTearDown(container.dispose);
  await container.read(authControllerProvider.future);
  container.listen(creativeActivityProvider, (_, _) {});
  await Future<void>.delayed(Duration.zero);
  return container;
}

void main() {
  setUp(() {
    CreativeActivity.interval = const Duration(days: 1);
  });

  test('switching to a new chat does not cancel image or video jobs', () async {
    final api = ActivityApi()..jobs = [job('queued'), job('processing', id: 'video-1', kind: 'video')];
    final container = await setup(api);
    expect(container.read(creativeActivityProvider).activeCount, 2);
    await container.read(chatControllerProvider.notifier).open(null);
    expect(container.read(creativeActivityProvider).activeCount, 2);
    api.jobs = [job('completed'), job('completed', id: 'video-1', kind: 'video')];
    await container.read(creativeActivityProvider.notifier).refresh();
    expect(container.read(creativeActivityProvider).activeCount, 0);
    expect(container.read(creativeActivityProvider).notice, contains('ready'));
    expect(api.cancels, 0);
  });

  test('an older active job stays tracked when it falls outside the gallery page', () async {
    final api = ActivityApi()..jobs = [job('processing', kind: 'video')];
    final container = await setup(api);
    api.jobs = [];
    api.details['job-1'] = job('completed', kind: 'video');
    await container.read(creativeActivityProvider.notifier).refresh();
    expect(api.detailRequests, ['job-1']);
    expect(container.read(creativeActivityProvider).notice, contains('video'));
  });

  test('a temporary connection failure keeps progress and never cancels the job', () async {
    final api = ActivityApi()..jobs = [job('processing')];
    final container = await setup(api);
    api.offline = true;
    await container.read(creativeActivityProvider.notifier).refresh();
    expect(container.read(creativeActivityProvider).activeCount, 1);
    expect(api.cancels, 0);
  });

  test('logging out discards an in-flight gallery response from the previous account', () async {
    final api = ActivityApi();
    final container = await setup(api);
    final pending = Completer<List<Map<String, dynamic>>>();
    api.pending = pending;
    final refresh = container.read(creativeActivityProvider.notifier).refresh();
    (container.read(authControllerProvider.notifier) as ActivityAuth).signOut();
    await Future<void>.delayed(Duration.zero);
    pending.complete([job('processing')]);
    await refresh;
    expect(container.read(creativeActivityProvider).jobs, isEmpty);
  });
}
