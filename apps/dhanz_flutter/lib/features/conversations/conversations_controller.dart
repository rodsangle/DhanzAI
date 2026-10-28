import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api/api_client.dart';
import '../../core/providers.dart';
import '../../models/models.dart';
import '../auth/auth_controller.dart';

class ConversationSearch extends Notifier<String> {
  @override
  String build() => '';

  void set(String query) => state = query;
}

final conversationSearchProvider = NotifierProvider<ConversationSearch, String>(ConversationSearch.new);

/// The signed-in user's conversations (pinned first, then most recent), filtered by the search box.
class ConversationsController extends AsyncNotifier<List<ConversationSummary>> {
  @override
  Future<List<ConversationSummary>> build() async {
    // Only re-fetch when the signed-in account changes, not on profile edits.
    final userId = ref.watch(authControllerProvider.select((s) => s.value?.id));
    if (userId == null) return const [];
    final query = ref.watch(conversationSearchProvider);
    return ref.read(apiClientProvider).conversations(query: query);
  }

  Future<void> refresh() async {
    ref.invalidateSelf();
    await future;
  }

  Future<void> rename(String id, String title) async {
    await ref.read(apiClientProvider).updateConversation(id, title: title);
    await refresh();
  }

  Future<void> setPinned(String id, bool pinned) async {
    await ref.read(apiClientProvider).updateConversation(id, pinned: pinned);
    await refresh();
  }

  Future<void> delete(String id) async {
    await ref.read(apiClientProvider).deleteConversation(id);
    final current = state.value ?? const [];
    state = AsyncData([
      for (final c in current)
        if (c.id != id) c,
    ]);
  }
}

final conversationsProvider = AsyncNotifierProvider<ConversationsController, List<ConversationSummary>>(
  ConversationsController.new,
);

/// Models and features the backend currently has configured.
final serverInfoProvider = FutureProvider<ServerInfo>((ref) async {
  final userId = ref.watch(authControllerProvider.select((s) => s.value?.id));
  if (userId == null) return (models: const <AiModel>[], features: const Features());
  return ref.read(apiClientProvider).serverInfo();
});

final modelsProvider = FutureProvider<List<AiModel>>(
  (ref) async => (await ref.watch(serverInfoProvider.future)).models,
);
