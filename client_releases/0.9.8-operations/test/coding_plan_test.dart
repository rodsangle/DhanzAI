import 'package:dhanz_ai/features/coding/coding_plan.dart';
import 'package:dhanz_ai/models/models.dart';
import 'package:flutter_test/flutter_test.dart';

CodingPlan plan() => CodingPlan(
  models: ['gpt-5-codex', 'gpt-4.1-mini'],
  repositories: [
    {'full_name': 'owner/demo', 'default_branch': 'main'},
  ],
  projects: [
    {'id': 'old-project', 'name': 'Earlier agent', 'status': 'failed'},
  ],
);

void main() {
  additionalPlanTests();
  test('typed Python request is collected without asking its runtime again', () {
    final p = plan();
    p.answer('Create a Python agent that reads CSV files');
    expect(p.question?.key, 'goal');
    p.answer('new', choice: true);
    p.answer('given', choice: true);
    p.answer('', choice: true);
    expect(p.question?.key, 'model');
    expect(p.answer('use gpt-5-codex please'), isNull);
    expect(p.question?.key, 'repair');
    p.answer('no');
    expect(p.question, isNull);
    expect(p.runtime, 'python');
    expect(p.automatic, isFalse);
    expect(p.instructions('Earlier chat details'), contains('CSV files'));
    expect(p.instructions('Earlier chat details'), contains('Earlier chat details'));
  });

  test('repository flow rejects unconnected names and unsafe paths and explains choices', () {
    final p = plan()..start('Update the Flutter app and its tests');
    p.answer('repository', choice: true);
    p.answer('given', choice: true);
    expect(p.answer('other/private'), isNotNull);
    expect(p.question?.key, 'repository');
    p.answer('owner/demo');
    p.answer('default');
    expect(p.answer('../outside.dart'), isNotNull);
    p.answer('apps/example/pubspec.yaml, apps/example/lib/main.dart');
    expect(p.question?.key, 'workdir');
    expect(p.question!.choices.any((c) => c.value == 'apps/example' && c.explanation.isNotEmpty), isTrue);
    p.answer('apps/example');
    expect(p.answer('nonexistent-model'), isNotNull);
    p.answer('gpt-5-codex', choice: true);
    p.answer('once', choice: true);
    expect(p.question, isNull);
    expect(p.automatic, isTrue);
    expect(p.runtime, 'flutter');
  });

  test('free requirements are retained while configuration is gathered', () {
    final p = plan()..start('Create a JavaScript website');
    p.answer('new', choice: true);
    p.answer('Support dark mode and an accessible contact form');
    expect(p.question?.key, 'repository');
    p.answer('Also include keyboard navigation');
    expect(p.question?.key, 'repository');
    expect(p.instructions(''), contains('accessible contact form'));
    expect(p.instructions(''), contains('keyboard navigation'));
    expect(() => p.instructions(List.filled(13000, 'x').join()), throwsFormatException);
  });

  test('changing a repair into a new task clears its old source project', () {
    final p = plan()..start('Repair my previous project');
    p.answer('repair', choice: true);
    p.answer('old-project', choice: true);
    expect(p.projectId, 'old-project');
    p.change('goal');
    p.answer('new', choice: true);
    expect(p.projectId, isNull);
    p.reset();
    expect(p.question?.key, 'task');
  });

  test('chat context is bounded and excludes hidden and unfinished messages', () {
    final context = codingChatContext([
      const ChatMessage(id: 'system', role: 'system', content: 'Hidden instructions', status: MessageStatus.complete),
      const ChatMessage(id: 'stream', role: 'assistant', content: 'Unfinished', status: MessageStatus.streaming),
      ChatMessage(
        id: 'user',
        role: 'user',
        content: List.filled(400, 'Useful requirements ').join(),
        status: MessageStatus.complete,
      ),
      const ChatMessage(id: 'last', role: 'assistant', content: 'Latest explanation', status: MessageStatus.complete),
    ]);
    expect(context.length, lessThanOrEqualTo(3500));
    expect(context, contains('Latest explanation'));
    expect(context, isNot(contains('Hidden instructions')));
    expect(context, isNot(contains('Unfinished')));
    expect(context, contains('[excerpt]'));
  });
}

void additionalPlanTests() {
  test('numbered requirement options wait for the typed detail rather than collecting the number', () {
    final p = plan()..start('Create an agent');
    p.answer('1');
    p.answer('2');
    expect(p.question?.key, 'requirements');
    expect(p.extraRequirements, isEmpty);
    p.answer('Also include a searchable task history');
    expect(p.question?.key, 'repository');
    expect(p.extraRequirements.single, contains('searchable task history'));
    p.answer('', choice: true);
    expect(p.question?.key, 'runtime');
    p.answer('JavaScript agent');
    expect(p.runtime, 'web');
  });
}
