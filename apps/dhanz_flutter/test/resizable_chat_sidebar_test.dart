import 'package:dhanz_ai/core/storage/secure_store.dart';
import 'package:dhanz_ai/features/conversations/resizable_chat_sidebar.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

Widget host(MemorySecureStore store, {double width = 1200, Key? panelKey}) => MaterialApp(
  home: Scaffold(
    body: Align(
      alignment: Alignment.topLeft,
      child: SizedBox(
        width: width,
        child: ResizableChatSidebar(
          key: panelKey,
          store: store,
          sidebar: const ColoredBox(color: Colors.blue),
          child: const Text('Chat remains available'),
        ),
      ),
    ),
  ),
);

double sidebarWidth(WidgetTester tester) => tester.getSize(find.byKey(const ValueKey('chat-history-width'))).width;

void main() {
  testWidgets('sidebar drag is bounded and saved across remounts', (tester) async {
    await tester.binding.setSurfaceSize(const Size(1200, 800));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final store = MemorySecureStore();
    await tester.pumpWidget(host(store));
    await tester.pumpAndSettle();
    expect(sidebarWidth(tester), 364);
    await tester.drag(find.byKey(const ValueKey('chat-history-resizer')), const Offset(1000, 0));
    await tester.pumpAndSettle();
    expect(sidebarWidth(tester), 520);
    expect(store.values[ResizableChatSidebar.storageKey], '520.0');
    await tester.pumpWidget(host(store, panelKey: const ValueKey('remount')));
    await tester.pumpAndSettle();
    expect(sidebarWidth(tester), 520);
    await tester.drag(find.byKey(const ValueKey('chat-history-resizer')), const Offset(-1000, 0));
    await tester.pumpAndSettle();
    expect(sidebarWidth(tester), 300);
    expect(tester.takeException(), isNull);
  });

  testWidgets('sidebar adapts to window width without discarding the preference', (tester) async {
    await tester.binding.setSurfaceSize(const Size(1200, 800));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final store = MemorySecureStore();
    store.values[ResizableChatSidebar.storageKey] = '520';
    await tester.pumpWidget(host(store, width: 900));
    await tester.pumpAndSettle();
    expect(sidebarWidth(tester), 408);
    expect(store.values[ResizableChatSidebar.storageKey], '520');
    await tester.pumpWidget(host(store));
    await tester.pumpAndSettle();
    expect(sidebarWidth(tester), 520);
    expect(tester.takeException(), isNull);
  });

  testWidgets('sidebar supports keyboard resizing and reset with invalid saved values', (tester) async {
    await tester.binding.setSurfaceSize(const Size(1200, 800));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final store = MemorySecureStore();
    store.values[ResizableChatSidebar.storageKey] = 'NaN';
    await tester.pumpWidget(host(store));
    await tester.pumpAndSettle();
    expect(sidebarWidth(tester), 364);
    await tester.sendKeyEvent(LogicalKeyboardKey.tab); // "Hide chat history" button
    await tester.sendKeyEvent(LogicalKeyboardKey.tab); // resize handle
    await tester.sendKeyEvent(LogicalKeyboardKey.arrowRight);
    await tester.pumpAndSettle();
    expect(sidebarWidth(tester), 388);
    await tester.sendKeyEvent(LogicalKeyboardKey.arrowLeft);
    await tester.pumpAndSettle();
    expect(sidebarWidth(tester), 364);
    await tester.sendKeyEvent(LogicalKeyboardKey.arrowRight);
    await tester.sendKeyEvent(LogicalKeyboardKey.home);
    await tester.pumpAndSettle();
    expect(sidebarWidth(tester), 364);
    final handle = find.byKey(const ValueKey('chat-history-resizer'));
    await tester.drag(handle, const Offset(80, 0));
    await tester.pumpAndSettle();
    await tester.tap(handle);
    await tester.pump(const Duration(milliseconds: 50));
    await tester.tap(handle);
    await tester.pumpAndSettle();
    expect(sidebarWidth(tester), 364);
    expect(tester.takeException(), isNull);
  });

  testWidgets('chat history collapses to a strip, expands again and remembers the choice', (tester) async {
    await tester.binding.setSurfaceSize(const Size(1200, 800));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final store = MemorySecureStore();
    await tester.pumpWidget(host(store));
    await tester.pumpAndSettle();
    await tester.tap(find.byTooltip('Hide chat history'));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('chat-history-width')), findsNothing);
    expect(tester.getSize(find.byKey(const ValueKey('chat-history-collapsed'))).width, 56);
    expect(find.text('Chat remains available'), findsOneWidget);
    expect(store.values[ResizableChatSidebar.collapsedKey], 'true');

    await tester.pumpWidget(host(store, panelKey: const ValueKey('remount')));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('chat-history-collapsed')), findsOneWidget); // remembered

    await tester.tap(find.byTooltip('Show chat history'));
    await tester.pumpAndSettle();
    expect(sidebarWidth(tester), 364);
    expect(store.values[ResizableChatSidebar.collapsedKey], 'false');
    expect(tester.takeException(), isNull);
  });
}
