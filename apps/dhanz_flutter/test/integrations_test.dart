import 'package:dhanz_ai/core/api/api_client.dart';
import 'package:dhanz_ai/core/providers.dart';
import 'package:dhanz_ai/core/storage/secure_store.dart';
import 'package:dhanz_ai/features/settings/integrations_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

class IntegrationApi extends ApiClient {
  IntegrationApi() : super(store: MemorySecureStore(), baseUrl: 'https://example.test');
  bool configured = false, connected = false;
  List<String> requested = [];
  final List<Map<String, dynamic>> actions = [];
  @override
  Future<Map<String, dynamic>> integrations() async => {
    'connections': [
      {
        'provider': 'microsoft',
        'configured': configured,
        'connected': connected,
        'account': 'owner@example.test',
        'services': ['files', 'mail'],
      },
      {'provider': 'google', 'configured': configured, 'connected': false, 'services': <String>[]},
    ],
  };
  @override
  Future<Map<String, dynamic>> integrationConnect(String provider, List<String> services) async {
    requested = services;
    return {'authorization_url': 'https://login.microsoftonline.com/common/oauth2/v2.0/authorize?state=test'};
  }

  @override
  Future<Map<String, dynamic>> integrationOperation(String provider, Map<String, dynamic> body) async {
    actions.add(body);
    if (body['operation'] == 'files') {
      return {
        'files': [
          {'id': 'one', 'name': 'Schedule.xlsx', 'folder': false},
        ],
      };
    }
    if (body['operation'] == 'import_file') return {'imported': true, 'filename': 'Schedule.xlsx'};
    return {'draft_created': true, 'sent': false};
  }
}

void main() {
  test('provider sign-in links reject lookalikes, credentials and unsafe schemes', () {
    expect(integrationSignInUri('https://accounts.google.com/o/oauth2/v2/auth'), isNotNull);
    expect(integrationSignInUri('https://login.microsoftonline.com/common/oauth2/v2.0/authorize'), isNotNull);
    for (final value in [
      'http://accounts.google.com',
      'https://accounts.google.com.evil.test',
      'https://user:secret@accounts.google.com',
      'javascript:alert(1)',
      'https://accounts.google.com:8443',
    ]) {
      expect(integrationSignInUri(value), isNull);
    }
  });
  testWidgets('unconfigured providers cannot start account sign-in', (tester) async {
    final api = IntegrationApi();
    await tester.pumpWidget(
      ProviderScope(
        overrides: [apiClientProvider.overrideWithValue(api)],
        child: const MaterialApp(home: IntegrationsScreen()),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('Microsoft 365'), findsOneWidget);
    final button = tester.widget<FilledButton>(find.widgetWithText(FilledButton, 'Connect').first);
    expect(button.onPressed, isNull);
    expect(find.textContaining('Server setup required'), findsWidgets);
  });
  testWidgets('connect requests selected permissions before showing provider button', (tester) async {
    final api = IntegrationApi()..configured = true;
    await tester.pumpWidget(
      ProviderScope(
        overrides: [apiClientProvider.overrideWithValue(api)],
        child: const MaterialApp(home: IntegrationsScreen()),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('Outlook mail'));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Connect').first);
    await tester.pumpAndSettle();
    expect(api.requested, ['files']);
    expect(find.text('Continue to Microsoft sign-in'), findsOneWidget);
  });
  testWidgets('cloud import requires selecting a file and uses an operation key', (tester) async {
    final api = IntegrationApi()
      ..configured = true
      ..connected = true;
    await tester.pumpWidget(
      ProviderScope(
        overrides: [apiClientProvider.overrideWithValue(api)],
        child: const MaterialApp(home: IntegrationsScreen()),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('Browse files'));
    await tester.pumpAndSettle();
    expect(api.actions.map((e) => e['operation']), ['files']);
    await tester.tap(find.text('Schedule.xlsx'));
    await tester.pumpAndSettle();
    expect(api.actions.last['operation'], 'import_file');
    expect(api.actions.last['remote_id'], 'one');
    expect(api.actions.last['request_key'], isNotEmpty);
    expect(find.textContaining('Imported Schedule.xlsx'), findsOneWidget);
    expect(api.actions.any((a) => a['operation'] == 'send_mail'), isFalse);
  });
}
