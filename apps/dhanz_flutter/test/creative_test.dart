import 'dart:convert';
import 'dart:typed_data';

import 'package:dhanz_ai/core/api/api_client.dart';
import 'package:dhanz_ai/core/providers.dart';
import 'package:dhanz_ai/core/storage/secure_store.dart';
import 'package:dhanz_ai/features/creative/studio_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

const imageModel = <String, dynamic>{
  'kind': 'image',
  'model': 'test-image',
  'provider': 'test',
  'ratios': ['1:1', '3:2'],
  'qualities': ['low', 'high'],
  'formats': ['png', 'webp'],
  'reference': true,
  'operations': ['generate', 'edit'],
  'durations': [],
  'resolutions': [],
};
const videoModel = <String, dynamic>{
  'kind': 'video',
  'model': 'gen4.5',
  'provider': 'runway',
  'ratios': ['16:9', '9:16'],
  'qualities': [],
  'formats': ['mp4'],
  'reference': true,
  'operations': ['generate'],
  'durations': [5, 10],
  'resolutions': ['720p'],
};

class StudioApi extends ApiClient {
  StudioApi() : super(store: MemorySecureStore(), baseUrl: 'https://studio.example');
  final bodies = <Map<String, dynamic>>[];
  final canceled = <String>[];
  final jobs = <Map<String, dynamic>>[];
  bool failNext = false;

  @override
  Future<Map<String, dynamic>> generateMedia(Map<String, dynamic> body) async {
    bodies.add(body);
    if (failNext) {
      failNext = false;
      throw ApiException(0, 'Connection interrupted');
    }
    final job = <String, dynamic>{
      'id': 'job-1',
      'kind': body['kind'],
      'model': body['model'],
      'status': 'queued',
      'prompt': body['prompt'],
      'cost': 5,
      'progress': 0,
      'has_media': false,
      'options': {'ratio': body['ratio'], 'format': body['format']},
    };
    jobs.add(job);
    return job;
  }

  @override
  Future<void> cancelCreation(String id) async {
    canceled.add(id);
    jobs.firstWhere((job) => job['id'] == id)['status'] = 'canceled';
  }
}

Future<void> mount(
  WidgetTester tester,
  StudioApi api, {
  List<Map<String, dynamic>> models = const [imageModel, videoModel],
  Size size = const Size(1280, 1200),
}) async {
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
  await tester.pumpWidget(
    ProviderScope(
      overrides: [
        apiClientProvider.overrideWithValue(api),
        studioProvider.overrideWith(
          (ref) async => (
            models: models,
            credits: <String, dynamic>{
              'balance': 100,
              'reserved': 0,
              'consumed': 0,
              'monthly_allowance': 100,
              'image_cost': 5,
              'video_cost_per_second': 10,
            },
            jobs: api.jobs,
          ),
        ),
      ],
      child: const MaterialApp(home: StudioScreen()),
    ),
  );
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('image workflow, durable gallery, cancellation and duplicate-click prevention', (tester) async {
    final api = StudioApi();
    await mount(tester, api);
    expect(find.text('DHANZ Creative Studio'), findsOneWidget);
    expect(find.textContaining('100 credits available'), findsOneWidget);
    await tester.enterText(find.byType(TextField).first, 'A mountain reflected in a lake');
    FocusManager.instance.primaryFocus?.unfocus();
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.byType(CheckboxListTile).first);
    await tester.tap(find.byType(CheckboxListTile).first);
    await tester.pump();
    await tester.ensureVisible(find.text('Generate · 5 credits'));
    await tester.tap(find.text('Generate · 5 credits'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));
    expect(api.bodies, hasLength(1));
    expect(api.bodies.first['rights_confirmed'], true);
    expect(api.bodies.first['ratio'], '1:1');
    expect(find.textContaining('test-image · queued'), findsOneWidget);
    await tester.tap(find.text('Cancel generation'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));
    expect(api.canceled, ['job-1']);
    expect(find.textContaining('test-image · canceled'), findsOneWidget);
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(const SizedBox());
    api.close();
  });

  testWidgets('network retry reuses the request key for the same prompt', (tester) async {
    final api = StudioApi()..failNext = true;
    await mount(tester, api);
    await tester.enterText(find.byType(TextField).first, 'An original landscape');
    FocusManager.instance.primaryFocus?.unfocus();
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.byType(CheckboxListTile).first);
    await tester.tap(find.byType(CheckboxListTile).first);
    await tester.pump();
    await tester.ensureVisible(find.text('Generate · 5 credits'));
    await tester.tap(find.text('Generate · 5 credits'));
    await tester.pumpAndSettle();
    expect(find.text('Connection interrupted'), findsOneWidget);
    await tester.tap(find.text('Generate · 5 credits'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));
    expect(api.bodies, hasLength(2));
    expect(api.bodies[0]['request_key'], api.bodies[1]['request_key']);
    await tester.pumpWidget(const SizedBox());
    api.close();
  });

  testWidgets('video form only shows supported settings and submits correct kind', (tester) async {
    final api = StudioApi();
    await mount(tester, api);
    await tester.tap(find.text('AI Videos'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField).last, 'A slow camera move across a forest');
    FocusManager.instance.primaryFocus?.unfocus();
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.byType(CheckboxListTile).last);
    await tester.tap(find.byType(CheckboxListTile).last);
    await tester.pump();
    await tester.ensureVisible(find.text('Generate · 50 credits'));
    await tester.tap(find.text('Generate · 50 credits'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));
    final body = api.bodies.single;
    expect(body['kind'], 'video');
    expect(body['duration'], 5);
    expect(body['resolution'], '720p');
    expect(body['format'], 'mp4');
    expect(body.containsKey('audio'), false);
    await tester.pumpWidget(const SizedBox());
    api.close();
  });

  testWidgets('unconfigured provider shows an honest unavailable message on a phone', (tester) async {
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final api = StudioApi();
    await mount(tester, api, models: [], size: const Size(390, 844));
    expect(find.textContaining('Image generation is not configured'), findsOneWidget);
    expect(find.text('Generate'), findsNothing);
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(const SizedBox());
    api.close();
  });

  test('API uses authenticated creative routes and downloads bytes', () async {
    final store = MemorySecureStore();
    await store.write(StoreKeys.accessToken, 'test-access');
    final seen = <http.Request>[];
    final api = ApiClient(
      store: store,
      baseUrl: 'https://studio.example',
      clientFactory: () => MockClient((request) async {
        seen.add(request);
        expect(request.headers['Authorization'], 'Bearer test-access');
        if (request.url.path.endsWith('/download')) return http.Response.bytes([1, 2, 3], 200);
        if (request.url.path.endsWith('/media-link')) {
          return http.Response(jsonEncode({'path': '/creative/media/id?signature=test'}), 200);
        }
        return http.Response(jsonEncode({'id': 'job-id'}), 201);
      }),
    );
    await api.generateMedia({'kind': 'image', 'prompt': 'Test', 'request_key': 'request-123'});
    expect(jsonDecode(seen.first.body)['request_key'], 'request-123');
    expect(seen.first.url.path, '/api/v1/creative/jobs');
    expect(await api.downloadCreation('job-id'), Uint8List.fromList([1, 2, 3]));
    expect(await api.creationMediaUrl('job-id'), 'https://studio.example/api/v1/creative/media/id?signature=test');
    api.close();
  });
}
