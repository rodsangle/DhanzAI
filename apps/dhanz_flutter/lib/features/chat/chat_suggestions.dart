import 'dart:math';

const _topics = [
  [
    'Explain a surprising fact about the ocean',
    'How do satellites stay in orbit?',
    'Teach me something interesting about ancient civilizations',
    'Explain how the human brain forms memories',
    'Why do we see different colors in a sunset?',
    'Help me understand how artificial intelligence learns',
    'Explain a science discovery in everyday language',
    'How do plants communicate with their surroundings?',
  ],
  [
    'Help me plan a relaxing weekend',
    'Suggest a simple habit I can start today',
    'Create a practical checklist for organizing my workspace',
    'Help me break a big goal into small steps',
    'Suggest a quick meal using ingredients I already have',
    'Help me make time for a new hobby',
    'Plan a productive morning without rushing',
    'Suggest five ways to learn something new this week',
  ],
  [
    'Give me a creative idea for a short story',
    'Help me write a thoughtful thank-you message',
    'Brainstorm names for a project I am starting',
    'Give me a fun photography challenge',
    'Help me turn an idea into a clear presentation',
    'Create a short poem about a fresh start',
    'Suggest an interesting topic for a friendly debate',
    'Ask me a question that sparks my imagination',
  ],
  [
    'Teach me a useful Excel formula with an example',
    'Explain a programming concept using a simple analogy',
    'Help me design a small personal project',
    'Give me a beginner-friendly coding challenge',
    'Explain how websites work behind the scenes',
    'Suggest ways to organize my digital files',
    'Help me compare two approaches to solving a problem',
    'Show me a practical way to automate a repetitive task',
  ],
];

List<String> randomChatSuggestions() {
  final random = Random();
  final suggestions = [for (final topic in _topics) topic[random.nextInt(topic.length)]];
  suggestions.shuffle(random);
  return List.unmodifiable(suggestions);
}
