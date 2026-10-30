import 'dart:convert';

import 'package:dhanz_ai/core/api/api_client.dart';
import 'package:dhanz_ai/core/providers.dart';
import 'package:dhanz_ai/core/storage/secure_store.dart';
import 'package:dhanz_ai/features/github/github_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

class GitHubApi extends ApiClient {
  GitHubApi() : super(store: MemorySecureStore(), baseUrl: 'https://dhanz.example');
  Map<String, dynamic> connection = {'configured': true, 'connected': false, 'repositories': []};
  String? receivedToken;
  List<String>? receivedRepos;
  bool fail = false;
  final queries = <Map<String, String>>[];

  @override
  Future<Map<String, dynamic>> githubConnection() async => connection;

  @override
  Future<Map<String, dynamic>> connectGithub(String token, List<String> repositories) async {
    receivedToken = token;
    receivedRepos = repositories;
    if (fail) throw ApiException(502, 'GitHub token expired');
    connection = {
      'configured': true,
      'connected': true,
      'login': 'ada',
      'repositories': [
        {'full_name': 'ada/project'},
      ],
    };
    return connection;
  }

  @override
  Future<void> disconnectGithub() async {
    connection = {'configured': true, 'connected': false, 'repositories': []};
  }

  @override
  Future<Map<String, dynamic>> readGithub(Map<String, String> query) async {
    queries.add(query);
    if (query['operation'] == 'directory') {
      return {
        'entries': [
          {'name': 'main.py', 'path': 'main.py', 'type': 'file'},
        ],
      };
    }
    return {
      'content': 'print("hello")',
      'path': 'main.py',
      'ref': 'main',
      'start_line': 1,
      'end_line': 1,
      'total_lines': 1,
    };
  }
}

Future<void> mount(WidgetTester tester, GitHubApi api, {Size size = const Size(1000, 1200)}) async {
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
  await tester.pumpWidget(
    ProviderScope(
      overrides: [apiClientProvider.overrideWithValue(api)],
      child: const MaterialApp(home: GitHubScreen()),
    ),
  );
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('connection requires consent, clears token and disconnects', (tester) async {
    final api = GitHubApi();
    await mount(tester, api);
    final save = find.widgetWithText(FilledButton, 'Save GitHub connection');
    expect(tester.widget<FilledButton>(save).onPressed, isNull);
    await tester.enterText(find.byType(TextField).first, 'secret-token');
    await tester.enterText(find.byType(TextField).at(1), 'ada/project');
    await tester.tap(find.byType(CheckboxListTile));
    await tester.pumpAndSettle();
    await tester.tap(save);
    await tester.pumpAndSettle();
    expect(api.receivedToken, 'secret-token');
    expect(api.receivedRepos, ['ada/project']);
    expect(tester.widget<TextField>(find.byType(TextField).first).controller!.text, isEmpty);
    expect(find.text('Connected as ada · Read-only'), findsOneWidget);
    await tester.tap(find.text('Disconnect GitHub'));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Disconnect'));
    await tester.pumpAndSettle();
    expect(api.connection['connected'], false);
  });

  testWidgets('connection errors do not retain the token', (tester) async {
    final api = GitHubApi()..fail = true;
    await mount(tester, api);
    await tester.enterText(find.byType(TextField).first, 'secret-token');
    await tester.enterText(find.byType(TextField).at(1), 'ada/project');
    await tester.tap(find.byType(CheckboxListTile));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Save GitHub connection'));
    await tester.pumpAndSettle();
    expect(find.text('GitHub token expired'), findsOneWidget);
    expect(tester.widget<TextField>(find.byType(TextField).first).controller!.text, isEmpty);
  });

  testWidgets('repository browser opens file content without rendering code', (tester) async {
    final api = GitHubApi();
    await api.connectGithub('token', ['ada/project']);
    await mount(tester, api);
    await tester.tap(find.byType(DropdownButtonFormField<String>));
    await tester.pumpAndSettle();
    await tester.tap(find.text('ada/project').last);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Browse folder'));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(ListTile, 'main.py').first);
    await tester.pumpAndSettle();
    expect(find.text('print("hello")'), findsOneWidget);
    expect(api.queries.last['repository'], 'ada/project');
    expect(api.queries.last['path'], 'main.py');
  });

  testWidgets('unconfigured connection fits phone and disables save', (tester) async {
    final api = GitHubApi()..connection = {'configured': false, 'connected': false, 'repositories': []};
    await mount(tester, api, size: const Size(390, 844));
    expect(find.textContaining('server administrator'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  test('API authenticates requests and refuses transmitting token over remote HTTP', () async {
    final store = MemorySecureStore();
    await store.write(StoreKeys.accessToken, 'dhanz-session');
    final requests = <http.Request>[];
    final api = ApiClient(
      store: store,
      baseUrl: 'https://dhanz.example',
      clientFactory: () => MockClient((request) async {
        requests.add(request);
        return http.Response(jsonEncode({'connected': true}), 200);
      }),
    );
    await api.connectGithub('private-token', ['ada/project']);
    expect(requests.single.method, 'PUT');
    expect(requests.single.headers['Authorization'], 'Bearer dhanz-session');
    expect(requests.single.url.toString(), isNot(contains('private-token')));
    expect(jsonDecode(requests.single.body)['token'], 'private-token');
    api.baseUrl = 'http://remote.example';
    await expectLater(api.connectGithub('private-token', ['ada/project']), throwsA(isA<ApiException>()));
    expect(requests.length, 1);
  });
}
