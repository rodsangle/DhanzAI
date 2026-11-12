import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';

import '../../core/api/api_client.dart';
import '../../core/providers.dart';
import '../../models/models.dart';
import '../auth/auth_controller.dart';

final adminStatsProvider = FutureProvider.autoDispose<AdminStats>((ref) => ref.watch(apiClientProvider).adminStats());

class AdminUserQuery extends Notifier<String> {
  @override
  String build() => '';

  void set(String value) => state = value;
}

final adminUserQueryProvider = NotifierProvider<AdminUserQuery, String>(AdminUserQuery.new);

final adminUsersProvider = FutureProvider.autoDispose<List<AdminUser>>((ref) {
  final q = ref.watch(adminUserQueryProvider).trim();
  return ref.watch(apiClientProvider).adminUsers(query: q.isEmpty ? null : q);
});

/// Server administration: usage overview and account management (administrators only).
class AdminScreen extends ConsumerWidget {
  const AdminScreen({super.key});

  Future<void> _update(
    BuildContext context,
    WidgetRef ref,
    AdminUser u, {
    bool? isActive,
    String? role,
    bool resetMfa = false,
  }) async {
    try {
      await ref.read(apiClientProvider).adminUpdateUser(u.id, isActive: isActive, role: role, resetMfa: resetMfa);
      ref
        ..invalidate(adminUsersProvider)
        ..invalidate(adminStatsProvider);
    } on ApiException catch (e) {
      if (context.mounted) {
        ScaffoldMessenger.of(context)
          ..clearSnackBars()
          ..showSnackBar(SnackBar(content: Text(e.message)));
      }
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    final me = ref.watch(authControllerProvider).value;
    final stats = ref.watch(adminStatsProvider);
    final users = ref.watch(adminUsersProvider);
    final numbers = NumberFormat.compact();

    Widget tile(String label, String value) => SizedBox(
      width: 160,
      child: Card(
        child: Padding(
          padding: const EdgeInsets.all(12),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(value, style: theme.textTheme.headlineSmall?.copyWith(color: theme.colorScheme.secondary)),
              Text(label, style: theme.textTheme.bodySmall),
            ],
          ),
        ),
      ),
    );

    return Scaffold(
      appBar: AppBar(
        title: const Text('Administration'),
        leading: IconButton(
          tooltip: 'Back',
          icon: const Icon(Icons.arrow_back),
          onPressed: () => context.go('/settings'),
        ),
        actions: [
          IconButton(
            tooltip: 'Refresh',
            icon: const Icon(Icons.refresh),
            onPressed: () => ref
              ..invalidate(adminStatsProvider)
              ..invalidate(adminUsersProvider),
          ),
        ],
      ),
      body: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 900),
          child: ListView(
            padding: const EdgeInsets.all(16),
            children: [
              stats.when(
                loading: () => const LinearProgressIndicator(),
                error: (e, _) => Text('Could not load statistics: $e'),
                data: (s) => Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Wrap(
                      spacing: 8,
                      runSpacing: 8,
                      children: [
                        tile('Accounts', '${s.users}'),
                        tile('Active (7 days)', '${s.activeUsers7d}'),
                        tile('Messages (24 h)', '${s.messages24h}'),
                        tile('Failed replies (24 h)', '${s.failedReplies24h}'),
                        tile('Conversations', '${s.conversations}'),
                        tile('Library documents', '${s.documents}'),
                      ],
                    ),
                    if (s.usage.isNotEmpty) ...[
                      const SizedBox(height: 16),
                      Text('AI usage, last 30 days', style: theme.textTheme.titleMedium),
                      for (final u in s.usage)
                        ListTile(
                          dense: true,
                          leading: const Icon(Icons.memory),
                          title: Text(u.provider),
                          subtitle: Text(
                            '${u.replies} replies · ${numbers.format(u.inputTokens)} input / '
                            '${numbers.format(u.outputTokens)} output tokens',
                          ),
                        ),
                    ],
                  ],
                ),
              ),
              const SizedBox(height: 24),
              Text('Accounts', style: theme.textTheme.titleMedium),
              const SizedBox(height: 8),
              TextField(
                decoration: const InputDecoration(prefixIcon: Icon(Icons.search), hintText: 'Search name or email'),
                onChanged: ref.read(adminUserQueryProvider.notifier).set,
              ),
              ...users.when(
                loading: () => [const Padding(padding: EdgeInsets.all(16), child: LinearProgressIndicator())],
                error: (e, _) => [Text('Could not load accounts: $e')],
                data: (list) => [
                  for (final u in list)
                    ListTile(
                      leading: Icon(u.role == 'admin' ? Icons.admin_panel_settings : Icons.person_outline),
                      title: Text(u.displayName),
                      subtitle: Text(
                        '${u.email} · ${u.conversations} chats · ${u.messages30d} messages in 30 days'
                        '${u.mfaEnabled ? ' · 2-step on' : ''}'
                        '${u.isActive ? '' : ' · deactivated'}',
                      ),
                      trailing: u.id == me?.id
                          ? const Chip(label: Text('You'))
                          : PopupMenuButton<String>(
                              tooltip: 'Manage ${u.displayName}',
                              onSelected: (action) => switch (action) {
                                'deactivate' => _update(context, ref, u, isActive: false),
                                'activate' => _update(context, ref, u, isActive: true),
                                'admin' => _update(context, ref, u, role: 'admin'),
                                'reset-mfa' => _update(context, ref, u, resetMfa: true),
                                _ => _update(context, ref, u, role: 'user'),
                              },
                              itemBuilder: (_) => [
                                PopupMenuItem(
                                  value: u.isActive ? 'deactivate' : 'activate',
                                  child: Text(u.isActive ? 'Deactivate account' : 'Reactivate account'),
                                ),
                                PopupMenuItem(
                                  value: u.role == 'admin' ? 'user' : 'admin',
                                  child: Text(u.role == 'admin' ? 'Remove administrator' : 'Make administrator'),
                                ),
                                // For someone who lost their phone and recovery codes: check who they are first.
                                if (u.mfaEnabled)
                                  const PopupMenuItem(
                                    value: 'reset-mfa',
                                    child: Text('Turn off two-step verification'),
                                  ),
                              ],
                            ),
                    ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}
