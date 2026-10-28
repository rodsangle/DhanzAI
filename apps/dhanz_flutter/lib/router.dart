import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import 'features/auth/auth_controller.dart';
import 'features/auth/auth_screen.dart';
import 'features/chat/chat_screen.dart';
import 'features/onboarding/splash_screen.dart';
import 'features/onboarding/welcome_screen.dart';
import 'features/settings/settings_screen.dart';

const _publicRoutes = {'/welcome', '/login', '/register'};

final routerProvider = Provider<GoRouter>((ref) {
  // Re-run redirects whenever the auth state changes.
  final authChanges = ValueNotifier<int>(0);
  ref.listen(authControllerProvider, (_, _) => authChanges.value++);
  ref.onDispose(authChanges.dispose);

  final router = GoRouter(
    initialLocation: '/splash',
    refreshListenable: authChanges,
    redirect: (context, state) {
      final auth = ref.read(authControllerProvider);
      final location = state.matchedLocation;
      if (auth.isLoading || auth.hasError) return location == '/splash' ? null : '/splash';
      final signedIn = auth.value != null;
      if (!signedIn) return _publicRoutes.contains(location) ? null : '/welcome';
      if (_publicRoutes.contains(location) || location == '/splash') return '/chat';
      return null;
    },
    routes: [
      GoRoute(path: '/splash', builder: (context, state) => const SplashScreen()),
      GoRoute(path: '/welcome', builder: (context, state) => const WelcomeScreen()),
      GoRoute(path: '/login', builder: (context, state) => const AuthScreen(register: false)),
      GoRoute(path: '/register', builder: (context, state) => const AuthScreen(register: true)),
      GoRoute(
        path: '/chat',
        pageBuilder: (context, state) => const NoTransitionPage(child: ChatScreen()),
        routes: [
          GoRoute(
            path: ':id',
            pageBuilder: (context, state) => NoTransitionPage(
              key: const ValueKey('chat'),
              child: ChatScreen(conversationId: state.pathParameters['id']),
            ),
          ),
        ],
      ),
      GoRoute(path: '/settings', builder: (context, state) => const SettingsScreen()),
    ],
  );
  ref.onDispose(router.dispose);
  return router;
});
