import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import '../lib/features/conversations/tool_navigation_rail.dart';

void main() {
  testWidgets('compact navigation uses tooltips and preserves each destination', (tester) async {
    String? selected;
    await tester.pumpWidget(MaterialApp(home: Scaffold(body: Align(
      alignment: Alignment.topLeft,
      child: SizedBox(height: 700, child: ToolNavigationRail(onNavigate: (route) => selected = route)),
    ))));
    expect(tester.getSize(find.byType(ToolNavigationRail)).width, 64);
    for (final destination in ToolNavigationRail.destinations) {
      expect(find.text(destination.label), findsNothing);
      final button = find.byTooltip(destination.label);
      await tester.ensureVisible(button);
      await tester.tap(button);
      expect(selected, destination.route);
    }
    final uploads = find.byTooltip('Uploads');
    await tester.ensureVisible(uploads);
    await tester.longPress(uploads);
    await tester.pumpAndSettle();
    expect(find.text('Uploads'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
