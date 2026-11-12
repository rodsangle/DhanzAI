import 'package:dhanz_ai/features/coding/coding_plan.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('status questions and acknowledgements do not start a paid coding build', () {
    expect(isCodingWorkRequest('How is the build going?'), false);
    expect(isCodingWorkRequest('Thanks'), false);
    expect(isCodingWorkRequest('Can you make the button larger?'), true);
    expect(isCodingWorkRequest('Start coding'), true);
  });
  test('discretion chooses routine defaults and preserves a private destination', () {
    final plan = CodingPlan(models: ['gpt-5-codex', 'gpt-4.1-mini']);
    plan.start('Build a web dashboard for tracking jobs');
    final choices = plan.useDiscretion();
    expect(choices, isNotEmpty);
    expect(plan.question, isNull);
    expect(plan.repository, isEmpty);
    expect(plan.model, 'gpt-5-codex');
    expect(plan.automatic, true);
  });
  test('discretion does not guess among multiple repository targets', () {
    final plan = CodingPlan(
      models: ['gpt-4.1-mini'],
      repositories: [
        {'full_name': 'owner/one'},
        {'full_name': 'owner/two'},
      ],
    );
    plan.start('Update my repository with a web dashboard');
    plan.useDiscretion();
    expect(plan.question?.key, 'repository');
    expect(plan.repository, isEmpty);
  });
  test('named repository is selected but source context must be inspected', () {
    final plan = CodingPlan(
      models: ['gpt-4.1-mini'],
      repositories: [
        {'full_name': 'owner/demo'},
      ],
    );
    plan.start('Add a status page to owner/demo');
    plan.useDiscretion();
    expect(plan.repository, 'owner/demo');
    expect(plan.question?.key, 'paths');
    plan.paths = ['README.md', 'package.json'];
    plan.useDiscretion();
    expect(plan.question, isNull);
  });
}
