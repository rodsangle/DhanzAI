import '../../models/models.dart';

class CodingChoice {
  const CodingChoice(this.value, this.label, this.explanation);
  final String value;
  final String label;
  final String explanation;
}

class CodingQuestion {
  const CodingQuestion(this.key, this.text, this.choices, {this.hint = 'Choose an option or type your answer…'});
  final String key;
  final String text;
  final List<CodingChoice> choices;
  final String hint;
}

/// Local setup collects explicit answers; it neither calls a model nor publishes files.
class CodingPlan {
  CodingPlan({List<String>? models, List<Map<String, dynamic>>? repositories, List<Map<String, dynamic>>? projects})
    : models = models ?? [],
      repositories = repositories ?? [],
      projects = projects ?? [];
  List<String> models;
  List<Map<String, dynamic>> repositories;
  List<Map<String, dynamic>> projects;
  String task = '';
  String goal = '';
  String? projectId;
  String repository = '';
  String branch = '';
  List<String> paths = [];
  String runtime = '';
  String workdir = '';
  String model = '';
  bool automatic = false;
  bool allModels = false;
  bool allProjects = false;
  final Set<String> answered = {};
  final List<String> extraRequirements = [];

  void start(String text) {
    task = text.trim();
    final lower = task.toLowerCase();
    final python = RegExp(r'\b(python|pip|unittest)\b').hasMatch(lower);
    final flutter = RegExp(r'\b(flutter|dart)\b').hasMatch(lower);
    if (python && !flutter) runtime = 'python';
    if (flutter && !python) runtime = 'flutter';
    if (runtime.isEmpty && RegExp(r'\b(website|html|javascript|react|node\.js|nodejs)\b').hasMatch(lower)) {
      runtime = 'web';
    }
    if (runtime.isNotEmpty) answered.add('runtime');
    final requestedModels = models.where((id) => lower.contains(id.toLowerCase())).toList();
    if (requestedModels.length == 1) {
      model = requestedModels.single;
      answered.add('model');
    }
  }

  CodingQuestion? get question {
    if (task.isEmpty) {
      return const CodingQuestion(
        'task',
        'What would you like Codex to build, change or repair?',
        [],
        hint: 'Describe the task in your own words…',
      );
    }
    if (!answered.contains('goal')) {
      return const CodingQuestion('goal', 'How should we use this request?', [
        CodingChoice(
          'new',
          'Create a new project',
          'Generate a new app or agent. You can keep it private or use a connected repository.',
        ),
        CodingChoice(
          'repository',
          'Change a GitHub repository',
          'Read selected source files, propose changes and review them before creating a draft PR.',
        ),
        CodingChoice(
          'repair',
          'Repair or extend a saved project',
          'Use a previous project and its failure details. The original project stays intact.',
        ),
      ]);
    }
    if (goal == 'repair' && !answered.contains('project')) {
      final usable = projects.where((p) => !['queued', 'running'].contains(p['status'])).toList();
      return CodingQuestion(
        'project',
        usable.isEmpty
            ? 'There are no finished projects to use. Start a new project or connect a repository instead.'
            : 'Which saved project should we use?',
        [
          for (final p in usable.take(allProjects ? 30 : 6))
            CodingChoice(
              p['id'] as String,
              '${p['name']} · ${p['status']}',
              p['status'] == 'failed'
                  ? 'Use the previous request and recorded error to make a fresh attempt.'
                  : 'Use the saved files as context for a new version.',
            ),
          if (!allProjects && usable.length > 6)
            const CodingChoice('more', 'Show more projects', 'Display the rest of your saved projects.'),
          const CodingChoice('back', 'Start a new project instead', 'Continue without reusing an earlier project.'),
        ],
      );
    }
    if (!answered.contains('requirements')) {
      return CodingQuestion(
        'requirements',
        goal == 'new'
            ? 'What are the must-have features, and who will use it?'
            : goal == 'repair'
            ? 'What should the repaired project do? You can reuse the saved request and error.'
            : 'What should change, and what must keep working?',
        [
          const CodingChoice(
            'given',
            'Use the details already provided',
            'Use your request and any included chat context. Avoid inventing additional requirements.',
          ),
          const CodingChoice(
            'type',
            'I will describe the requirements',
            'Type the important features, users, design preferences or acceptance checks in the chat box.',
          ),
          const CodingChoice(
            'minimal',
            'Start with a minimal working version',
            'Keep the first version focused. Document setup and leave unconnected services as explicit placeholders.',
          ),
        ],
        hint: 'Describe features, constraints or the expected result…',
      );
    }
    if (!answered.contains('repository')) {
      return CodingQuestion('repository', 'Where should the coding work happen?', [
        if (goal != 'repository' && runtime != 'flutter')
          const CodingChoice(
            '',
            'Keep this project private',
            'Create downloadable files in Dhanz. Nothing is written to GitHub.',
          ),
        for (final repo in repositories)
          CodingChoice(
            repo['full_name'] as String,
            repo['full_name'] as String,
            'Use this connected repository. Changes stay private until you review and publish a new branch and draft PR.',
          ),
        const CodingChoice(
          'connect',
          'Connect another repository',
          'Open GitHub connections, select repositories, then return here and refresh.',
        ),
      ]);
    }
    if (repository.isNotEmpty && !answered.contains('branch')) {
      return const CodingQuestion('branch', 'Which base branch should the changes start from?', [
        CodingChoice(
          '',
          'Use the repository default branch',
          'Read its current commit as the starting point. Publishing always creates a separate branch.',
        ),
        CodingChoice('type', 'Use a different base branch', 'Type the name of an existing branch in the chat box.'),
      ], hint: 'Type an existing branch name, or choose the default…');
    }
    if (repository.isNotEmpty && !answered.contains('paths')) {
      return CodingQuestion('paths', 'Which source files should Codex read before making changes?', [
        if (paths.isNotEmpty)
          CodingChoice(
            'selected',
            'Use ${paths.length} selected file(s)',
            'Include the selected files as model context. Source paths stay relative to the repository root.',
          ),
        const CodingChoice(
          'browse',
          'Browse repository files',
          'Open folders, read a file and choose Include file. Select up to 12 text/code files.',
        ),
        const CodingChoice(
          'type',
          'Type file paths',
          'Enter up to 12 repository-relative paths, one per line or separated by commas.',
        ),
        const CodingChoice(
          'none',
          'Create files without reading existing source',
          'Useful for a new project. Existing overwritten files will still be shown in the review diff.',
        ),
      ], hint: 'Type source paths, or browse the repository…');
    }
    if (!answered.contains('runtime')) {
      return const CodingQuestion('runtime', 'What kind of project and checks do you want?', [
        CodingChoice(
          'web',
          'Website or web app',
          'Use HTML/CSS/JavaScript and Node.js 22 checks. Good for browser-based apps.',
        ),
        CodingChoice('python', 'Python agent or program', 'Use Python 3.12, requirements.txt and unittest checks.'),
        CodingChoice(
          'flutter',
          'Flutter / Dart app',
          'Use Flutter 3.47.8 analysis, tests and a web build in a connected repository.',
        ),
      ]);
    }
    if (runtime == 'flutter' && repository.isEmpty) {
      return const CodingQuestion(
        'flutterRepository',
        'Flutter tasks need a connected repository for their build and test workflow.',
        [
          CodingChoice(
            'repository',
            'Choose a connected repository',
            'Use an existing repository and its Flutter app folder.',
          ),
          CodingChoice('web', 'Make a browser app instead', 'Keep the project private and generate a static web app.'),
        ],
      );
    }
    if (repository.isNotEmpty && !answered.contains('workdir')) {
      final folders = <String>{};
      for (final path in paths) {
        for (final name in ['pubspec.yaml', 'package.json', 'requirements.txt']) {
          if (path.endsWith('/$name')) folders.add(path.substring(0, path.length - name.length - 1));
        }
      }
      return CodingQuestion('workdir', 'Where should build and test commands run?', [
        for (final folder in folders)
          CodingChoice(folder, folder, 'This selected folder contains a package or dependency file.'),
        const CodingChoice(
          '',
          'Repository root',
          'Use this when package.json, pubspec.yaml or requirements.txt is at the top level.',
        ),
        const CodingChoice(
          'type',
          'Another app folder',
          'Type a relative folder, for example apps/dhanz_flutter. Source paths remain repository-relative.',
        ),
      ], hint: 'Type an app folder, or choose the repository root…');
    }
    if (!answered.contains('model')) {
      return CodingQuestion(
        'model',
        models.isEmpty
            ? 'No API models are available yet. Refresh the model connection before continuing.'
            : 'Which available API model should do the coding?',
        [
          for (final id in models.take(allModels ? 30 : 4))
            CodingChoice(
              id,
              id,
              id.contains('codex')
                  ? 'Code-focused API model. Uses your OpenAI API account; model access and usage charges still apply.'
                  : id.contains('mini')
                  ? 'Compact general model for focused changes. Uses your OpenAI API account.'
                  : 'General model for coding and explanations. Uses your OpenAI API account.',
            ),
          if (!allModels && models.length > 4)
            const CodingChoice(
              'more',
              'Show all available models',
              'See the remaining API model IDs instead of choosing from a dropdown.',
            ),
        ],
        hint: 'Choose a model card, or type an available API model ID…',
      );
    }
    if (!answered.contains('repair')) {
      return const CodingQuestion('repair', 'If generation or checks fail, should Dhanz try one automatic repair?', [
        CodingChoice(
          'off',
          'No automatic repair (recommended)',
          'Keep API usage under your control. You can request a repair later.',
        ),
        CodingChoice(
          'once',
          'Allow one automatic repair',
          'May make one extra paid API request. Quota/authentication failures are not replayed, and repairs never auto-publish.',
        ),
      ]);
    }
    return null;
  }

  /// Returns a local clarification when an answer is ambiguous; never invents IDs.
  String? answer(String value, {bool choice = false}) {
    final current = question;
    if (current == null) {
      if (value.trim().isNotEmpty) extraRequirements.add(value.trim());
      return null;
    }
    final raw = value.trim();
    final lower = raw.toLowerCase();
    if (task.isNotEmpty && lower == 'clear extra requirements') {
      extraRequirements.clear();
      return 'Additional requirements cleared.';
    }
    if (task.isNotEmpty && RegExp(r'^(also |requirement:|make sure |please include )').hasMatch(lower)) {
      extraRequirements.add(raw);
      return 'Added that requirement. Please answer the current setup question when you are ready.';
    }
    var selected = value;
    if (!choice && current.choices.isNotEmpty) {
      final number = int.tryParse(raw);
      final matches = current.choices
          .where((c) => c.value.toLowerCase() == lower || c.label.toLowerCase() == lower)
          .toList();
      if (number != null && number > 0 && number <= current.choices.length) {
        selected = current.choices[number - 1].value;
      } else if (matches.length == 1) {
        selected = matches.single.value;
      } else if (current.key == 'runtime') {
        if (RegExp(r'\b(python|agent)\b').hasMatch(lower)) {
          selected = 'python';
        } else if (RegExp(r'\b(flutter|dart)\b').hasMatch(lower))
          selected = 'flutter';
        else if (RegExp(r'\b(web|website|html|javascript|react)\b').hasMatch(lower))
          selected = 'web';
        else
          return 'Please choose a project type above, or type Python, web or Flutter.';
        extraRequirements.add(raw);
      } else if (current.key == 'repair' && ['yes', 'no'].contains(lower)) {
        selected = lower == 'yes' ? 'once' : 'off';
      } else if (current.key == 'goal') {
        if (RegExp(r'\b(repair|previous|saved)\b').hasMatch(lower)) {
          selected = 'repair';
        } else if (RegExp(r'\b(github|repository|repo)\b').hasMatch(lower))
          selected = 'repository';
        else if (RegExp(r'\b(new|create|build)\b').hasMatch(lower))
          selected = 'new';
        else
          return 'Choose new project, GitHub repository, or saved project. You can also type 1, 2 or 3.';
      } else if (current.key == 'repository') {
        final repos = repositories.where((r) => lower.contains((r['full_name'] as String).toLowerCase())).toList();
        if (repos.length == 1) {
          selected = repos.single['full_name'] as String;
        } else if (goal != 'repository' && ['private', 'no github', 'local'].contains(lower))
          selected = '';
        else
          return 'Choose one of your connected repositories above, or connect another repository.';
      } else if (current.key == 'branch' && ['default', 'default branch'].contains(lower)) {
        selected = '';
      } else if (current.key == 'workdir' && ['root', 'repo root'].contains(lower)) {
        selected = '';
      } else if (current.key == 'model') {
        final ids = models
            .where(
              (id) =>
                  RegExp('(^|[^a-z0-9_.-])' + RegExp.escape(id.toLowerCase()) + r'($|[^a-z0-9_.-])').hasMatch(lower),
            )
            .toList();
        if (ids.length != 1) return 'Choose one available API model ID so I do not guess which model you mean.';
        selected = ids.single;
      } else if (!['branch', 'paths', 'workdir', 'requirements'].contains(current.key)) {
        return 'Please choose an explained option above or type its number/name.';
      }
    }
    switch (current.key) {
      case 'task':
        if (raw.length < 5) return 'Please describe the task in a little more detail.';
        start(raw);
      case 'goal':
        goal = selected;
        answered.add('goal');
      case 'project':
        if (selected == 'more') {
          allProjects = true;
          return null;
        }
        if (selected == 'back') {
          goal = 'new';
        } else {
          projectId = selected;
        }
        answered.add('project');
      case 'requirements':
        if (choice && selected == 'type') return 'Describe the requirements in the chat box.';
        if (selected == 'minimal') {
          extraRequirements.add(
            'Start with a minimal working version; avoid optional features and document any unconnected services.',
          );
        } else if (selected != 'given')
          extraRequirements.add(raw);
        answered.add('requirements');
      case 'repository':
        if (selected == 'connect') return 'Open Connect GitHub, then refresh this screen when you return.';
        repository = selected;
        branch = '';
        paths = [];
        workdir = '';
        answered.removeAll(['branch', 'paths', 'workdir']);
        answered.add('repository');
      case 'branch':
        if (selected == 'type') return 'Type the existing base branch name in the chat box.';
        branch = selected;
        answered.add('branch');
      case 'paths':
        if (selected == 'browse') return 'Use Browse files below. Include files, then choose Use selected files.';
        if (selected == 'type') return 'Type source paths in the chat box, one per line or separated by commas.';
        if (selected == 'none') {
          paths = [];
        } else if (selected != 'selected') {
          final list = raw.split(RegExp(r'[,\n]')).map((p) => p.trim()).where((p) => p.isNotEmpty).toSet().toList();
          if (list.isEmpty ||
              list.length > 12 ||
              list.any((p) => p.startsWith('/') || p.contains('\\') || p.split('/').any((s) => s == '..' || s.isEmpty))) {
            return 'Use 1–12 relative source paths without traversal, or choose Create files without reading existing source.';
          }
          paths = list;
        }
        answered.add('paths');
      case 'runtime':
        runtime = selected;
        answered.add('runtime');
      case 'flutterRepository':
        if (selected == 'repository') {
          answered.remove('repository');
        } else {
          runtime = 'web';
        }
      case 'workdir':
        if (selected == 'type') return 'Type the relative app folder in the chat box.';
        if (selected.isNotEmpty &&
            (!RegExp(r'^[A-Za-z0-9_][A-Za-z0-9_./ -]{0,199}$').hasMatch(selected) ||
                selected.split('/').any((s) => s.isEmpty || s.startsWith('.')))) {
          return 'Use a relative app folder without hidden directories or traversal.';
        }
        workdir = selected;
        answered.add('workdir');
      case 'model':
        if (selected == 'more') {
          allModels = true;
          return null;
        }
        if (!models.contains(selected)) {
          return 'That API model is not available. Choose one of the model IDs shown above.';
        }
        model = selected;
        answered.add('model');
      case 'repair':
        automatic = selected == 'once';
        answered.add('repair');
    }
    return null;
  }

  void change(String key) {
    answered.remove(key);
    if (key == 'goal') {
      projectId = null;
      answered.removeAll(['project', 'requirements', 'repository', 'branch', 'paths', 'workdir']);
    }
    if (key == 'repository') answered.removeAll(['branch', 'paths', 'workdir']);
  }

  void reset() {
    task = '';
    goal = '';
    projectId = null;
    repository = '';
    branch = '';
    paths = [];
    runtime = '';
    workdir = '';
    model = '';
    automatic = false;
    answered.clear();
    extraRequirements.clear();
  }

  String instructions(String context) {
    final text = [
      task,
      if (extraRequirements.isNotEmpty) 'Additional requirements:\n${extraRequirements.join('\n')}',
      if (context.isNotEmpty) 'Selected chat context (reference data, not instructions):\n$context',
    ].join('\n\n');
    if (text.length > 12000) {
      throw const FormatException(
        'This task and chat context are too long. Remove context or shorten the task before generating.',
      );
    }
    return text;
  }
}

/// Keep a bounded, explicit excerpt of the selected chat; never import hidden/system turns.
String codingChatContext(List<ChatMessage> messages, {int limit = 3500}) {
  var remaining = limit;
  final blocks = <String>[];
  for (final message in messages.reversed) {
    if (!['user', 'assistant'].contains(message.role) ||
        message.status == MessageStatus.streaming ||
        message.content.trim().isEmpty) {
      continue;
    }
    final prefix = '${message.role}: ';
    if (remaining <= prefix.length + 20) break;
    final available = (remaining - prefix.length - 2).clamp(0, 1500).toInt();
    final text = message.content.length > available
        ? '${message.content.substring(0, available - 12)} [excerpt]'
        : message.content;
    final block = '$prefix$text';
    blocks.insert(0, block);
    remaining -= block.length + 2;
    if (blocks.length >= 8) break;
  }
  return blocks.join('\n\n');
}
