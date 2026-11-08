import 'dart:convert';
import 'dart:typed_data';
import 'package:dhanz_ai/core/api/api_client.dart';
import 'package:dhanz_ai/core/storage/secure_store.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
void main() {
  test('reference upload and optional analysis never implicitly generate video', () async {
    final requests = <http.Request>[];
    final api = ApiClient(store: MemorySecureStore(), baseUrl: 'https://example.test', clientFactory: () => MockClient((request) async {
      requests.add(request);
      if (request.url.path.endsWith('/upload')) {
        expect(request.body, contains('filename="clip.mp4"'));
        expect(request.body, contains('name="video"'));
        return http.Response(jsonEncode({'id': 'ref-one', 'reference_id': 'image-one', 'duration': 2, 'frames': [], 'timestamps': []}), 201);
      }
      expect(request.url.path, endsWith('/ref-one/analyze'));
      expect(jsonDecode(request.body)['retry'], isFalse);
      return http.Response(jsonEncode({'brief': 'Gentle camera pan'}), 200);
    }));
    await expectLater(api.uploadReferenceVideo('clip.mp4', Uint8List(1), isCurrentSession: () => false), throwsA(isA<ApiException>()));
    expect(requests, isEmpty);
    final result = await api.uploadReferenceVideo('clip.mp4', Uint8List.fromList([1, 2, 3]));
    expect(result['reference_id'], 'image-one');
    expect(requests.length, 1);
    expect(await api.analyzeReferenceVideo('ref-one'), 'Gentle camera pan');
    expect(requests.length, 2);
    expect(requests.any((r) => r.url.path.contains('/creative/jobs')), isFalse);
    api.close();
  });
}
