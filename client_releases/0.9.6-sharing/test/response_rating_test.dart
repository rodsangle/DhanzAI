import 'package:dhanz_ai/core/api/api_client.dart';
import 'package:dhanz_ai/core/providers.dart';
import 'package:dhanz_ai/core/storage/secure_store.dart';
import 'package:dhanz_ai/features/auth/auth_controller.dart';
import 'package:dhanz_ai/features/chat/response_rating.dart';
import 'package:dhanz_ai/models/models.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

class SignedInAuth extends AuthController {
  @override
  Future<User?> build() async => const User(
    id: 'owner',
    email: 'owner@example.test',
    displayName: 'Owner',
    role: 'user',
    routingPolicy: 'balanced',
  );
}

class FeedbackApi extends ApiClient {
  FeedbackApi() : super(store: MemorySecureStore(), baseUrl: 'https://example.test');
  String? rating;
  bool fail = false;
  @override
  Future<Map<String, dynamic>> responseFeedback(String id) async => {'rating': rating};
  @override
  Future<void> rateResponse(String id, String? value) async {
    if (fail) throw ApiException(503, 'Feedback could not be saved');
    rating = value;
  }
}

void main() {
  testWidgets('ratings reflect persisted feedback and a second click clears it', (tester) async {
    final api = FeedbackApi();
    await tester.pumpWidget(
      ProviderScope(
        overrides: [apiClientProvider.overrideWithValue(api), authControllerProvider.overrideWith(SignedInAuth.new)],
        child: const MaterialApp(
          home: Scaffold(body: ResponseRating(messageId: 'reply')),
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.byTooltip('Good response'));
    await tester.pumpAndSettle();
    expect(api.rating, 'up');
    expect(find.byIcon(Icons.thumb_up), findsOneWidget);
    await tester.tap(find.byTooltip('Good response'));
    await tester.pumpAndSettle();
    expect(api.rating, isNull);
    expect(find.byIcon(Icons.thumb_up_outlined), findsOneWidget);
    api.fail = true;
    await tester.tap(find.byTooltip('Poor response'));
    await tester.pumpAndSettle();
    expect(api.rating, isNull);
    expect(find.byIcon(Icons.thumb_down_outlined), findsOneWidget);
    await tester.pumpWidget(const SizedBox.shrink());
    api.close();
  });
}
