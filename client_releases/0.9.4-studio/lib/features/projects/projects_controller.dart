import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/providers.dart';
import '../../models/models.dart';
import '../auth/auth_controller.dart';

class ProjectsController extends AsyncNotifier<List<Project>> {
  @override
  Future<List<Project>> build() async {
    final userId = ref.watch(authControllerProvider.select((s) => s.value?.id));
    if (userId == null) return const [];
    return ref.read(apiClientProvider).projects();
  }

  Future<Project> create(String name, {String? description, String? instructions}) async {
    final project = await ref
        .read(apiClientProvider)
        .createProject(name, description: description, instructions: instructions);
    state = AsyncData([...state.value ?? const <Project>[], project]..sort((a, b) => a.name.compareTo(b.name)));
    return project;
  }

  Future<void> save(String id, {required String name, String? description, String? instructions}) async {
    final updated = await ref
        .read(apiClientProvider)
        .updateProject(id, name: name, description: description ?? '', instructions: instructions ?? '');
    state = AsyncData([for (final p in state.value ?? const <Project>[]) p.id == id ? updated : p]);
  }

  Future<void> delete(String id) async {
    await ref.read(apiClientProvider).deleteProject(id);
    state = AsyncData([
      for (final p in state.value ?? const <Project>[])
        if (p.id != id) p,
    ]);
    if (ref.read(selectedProjectProvider) == id) ref.read(selectedProjectProvider.notifier).select(null);
  }
}

final projectsProvider = AsyncNotifierProvider<ProjectsController, List<Project>>(ProjectsController.new);

/// The project the user is working in (null = all chats). New chats and uploads go into it.
class SelectedProject extends Notifier<String?> {
  @override
  String? build() {
    ref.watch(authControllerProvider.select((s) => s.value?.id));
    return null;
  }

  void select(String? projectId) => state = projectId;
}

final selectedProjectProvider = NotifierProvider<SelectedProject, String?>(SelectedProject.new);
