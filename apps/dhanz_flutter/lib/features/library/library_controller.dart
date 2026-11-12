import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/providers.dart';
import '../../models/models.dart';
import '../auth/auth_controller.dart';

class LibraryController extends AsyncNotifier<List<KnowledgeDocument>> {
  @override
  Future<List<KnowledgeDocument>> build() async {
    final userId = ref.watch(authControllerProvider.select((s) => s.value?.id));
    if (userId == null) return const [];
    return ref.read(apiClientProvider).documents();
  }

  Future<void> add(String url) async {
    final doc = await ref.read(apiClientProvider).addDocument(url);
    final current = state.value ?? const [];
    state = AsyncData([
      doc,
      for (final d in current)
        if (d.id != doc.id) d,
    ]);
  }

  void addLocal(KnowledgeDocument doc) => state = AsyncData([
    doc,
    for (final d in state.value ?? const <KnowledgeDocument>[])
      if (d.id != doc.id) d,
  ]);

  Future<void> remove(String id) async {
    await ref.read(apiClientProvider).deleteDocument(id);
    state = AsyncData([
      for (final d in state.value ?? const <KnowledgeDocument>[])
        if (d.id != id) d,
    ]);
  }

  Future<void> refresh() async {
    ref.invalidateSelf();
    await future;
  }
}

final libraryProvider = AsyncNotifierProvider<LibraryController, List<KnowledgeDocument>>(LibraryController.new);
