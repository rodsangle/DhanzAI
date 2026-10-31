import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/api/api_client.dart';
import '../../core/api/ollama_client.dart';
import '../../core/providers.dart';
import '../auth/auth_controller.dart';

/// Session-only desktop chat. Local mode makes no backend requests.
class LocalChatScreen extends ConsumerStatefulWidget {
  const LocalChatScreen({super.key});
  @override
  ConsumerState<LocalChatScreen> createState() => _LocalChatScreenState();
}

class _LocalChatScreenState extends ConsumerState<LocalChatScreen> {
  final _ollama = OllamaClient();
  final _input = TextEditingController();
  final _messages = <Map<String, String>>[];
  AiRoute _route = AiRoute.local;
  String _model = localModels.first;
  String _status = 'Ready';
  bool _busy = false;
  bool _testing = false;
  int _generation = 0;
  ChatStream? _cloud;
  ApiClient? _cloudApi;
  String? _cloudId;

  @override
  void dispose() {
    _generation++;
    _ollama.cancel();
    _cloud?.cancel();
    final id = _cloudId;
    final api = _cloudApi;
    if (id != null && api != null) {
      unawaited(api.stopReply(id).catchError((Object _) {}));
    }
    _input.dispose();
    super.dispose();
  }

  Future<void> _test() async {
    setState(() => _testing = true);
    try {
      await _ollama.testConnection(_model);
      if (mounted) setState(() => _status = 'Connected: $_model is installed');
    } on Exception catch (e) {
      if (mounted) setState(() => _status = '$e');
    } finally {
      if (mounted) setState(() => _testing = false);
    }
  }

  Stream<String> _cloudReply(List<Map<String, String>> history, int generation) async* {
    if (!mounted || generation != _generation) return;
    if (ref.read(authControllerProvider).value == null) {
      throw const LocalAiException('Sign in from the welcome screen to use Cloud or Hybrid fallback.');
    }
    final api = ref.read(apiClientProvider);
    _cloudApi = api;
    // Include local turns when switching providers. Each turn is independent on the
    // backend so that a failed local attempt never creates a duplicate cloud turn.
    final conversation = await api.createConversation(temporary: true);
    if (!mounted || generation != _generation) return;
    _cloudId = conversation.id;
    final stream = await api.streamChat(
      conversation.id,
      content: history.map((m) => '${m['role']}: ${m['content']}').join('\n\n'),
    );
    if (!mounted || generation != _generation) {
      stream.cancel();
      unawaited(api.stopReply(conversation.id).catchError((Object _) {}));
      return;
    }
    _cloud = stream;
    var completed = false;
    try {
      await for (final event in stream.events) {
        if (event.type == 'delta') yield event.data['text'] as String;
        if (event.type == 'error') throw ApiException(0, event.data['detail'] as String? ?? 'Cloud generation failed.');
        if (event.type == 'done' || event.type == 'stopped') completed = true;
      }
      if (!completed) throw const LocalAiException('Cloud connection lost. Retry when online.');
    } finally {
      stream.cancel();
      if (identical(_cloud, stream)) _cloud = null;
    }
  }

  Future<void> _send() async {
    final text = _input.text.trim();
    if (_busy || text.isEmpty) return;
    final generation = ++_generation;
    _cloudId = null;
    final route = _route;
    final model = _model;
    _input.clear();
    _messages.add({'role': 'user', 'content': text});
    final history = [for (final m in _messages) Map<String, String>.from(m)];
    _messages.add({'role': 'assistant', 'content': ''});
    setState(() => _busy = true);
    try {
      await for (final delta in routeReply(
        route: route,
        local: () => _ollama.stream(history, model),
        cloud: () => _cloudReply(history, generation),
        onRoute: (label) {
          if (mounted && generation == _generation) setState(() => _status = label);
        },
      )) {
        if (!mounted || generation != _generation) return;
        setState(() => _messages.last['content'] = '${_messages.last['content']}$delta');
      }
      if (mounted && generation == _generation) setState(() => _status = '$_status · Complete');
    } on Exception catch (e) {
      if (mounted && generation == _generation) {
        setState(() {
          _status = '$e';
          if (_messages.last['content']!.isEmpty) {
            _messages.removeLast();
            _messages.removeLast();
            _input.text = text;
          }
        });
      }
    } finally {
      if (mounted && generation == _generation) setState(() => _busy = false);
    }
  }

  void _stop() {
    _generation++;
    _ollama.cancel();
    _cloud?.cancel();
    final id = _cloudId;
    _cloudId = null;
    if (id != null) {
      unawaited(ref.read(apiClientProvider).stopReply(id).catchError((Object _) {}));
    }
    setState(() {
      _busy = false;
      _status = 'Stopped · partial reply kept';
    });
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(
      title: const Text('DHANZ AI · Local / Cloud'),
      leading: IconButton(icon: const Icon(Icons.arrow_back), onPressed: () => context.go('/welcome')),
    ),
    body: Center(
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 900),
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            children: [
              Wrap(
                spacing: 16,
                runSpacing: 8,
                crossAxisAlignment: WrapCrossAlignment.center,
                children: [
                  DropdownButton<AiRoute>(
                    value: _route,
                    items: [
                      for (final route in AiRoute.values)
                        DropdownMenuItem(
                          value: route,
                          child: Text(switch (route) {
                            AiRoute.local => 'Local',
                            AiRoute.cloud => 'Cloud',
                            AiRoute.hybrid => 'Hybrid',
                          }),
                        ),
                    ],
                    onChanged: _busy ? null : (v) => setState(() => _route = v!),
                  ),
                  DropdownButton<String>(
                    value: _model,
                    items: [for (final model in localModels) DropdownMenuItem(value: model, child: Text(model))],
                    onChanged: _busy || _testing ? null : (v) => setState(() => _model = v!),
                  ),
                  OutlinedButton(
                    onPressed: _busy || _testing ? null : _test,
                    child: Text(_testing ? 'Testing…' : 'Test connection'),
                  ),
                  TextButton(
                    onPressed: _busy
                        ? null
                        : () => setState(() {
                            _messages.clear();
                            _input.clear();
                          }),
                    child: const Text('New chat'),
                  ),
                ],
              ),
              Text(
                _route == AiRoute.hybrid
                    ? 'Hybrid tries local first. If unavailable, your conversation is sent to your FastAPI server.'
                    : _route == AiRoute.local
                    ? 'Local chat stays on this PC. Internet and sign-in are not required.'
                    : 'Cloud uses your existing FastAPI server and account.',
              ),
              const Text(
                'This workspace keeps history only until you leave. Use the main cloud chat for files, tools and saved conversations.',
              ),
              const SizedBox(height: 8),
              SelectableText(_status),
              Expanded(
                child: ListView.builder(
                  itemCount: _messages.length,
                  itemBuilder: (context, i) => ListTile(
                    title: Text(_messages[i]['role'] == 'user' ? 'You' : 'DHANZ AI'),
                    subtitle: SelectableText(_messages[i]['content']!),
                  ),
                ),
              ),
              TextField(
                controller: _input,
                minLines: 1,
                maxLines: 5,
                enabled: !_busy,
                decoration: const InputDecoration(labelText: 'Message'),
                onSubmitted: (_) => _send(),
              ),
              const SizedBox(height: 8),
              FilledButton(onPressed: _busy ? _stop : _send, child: Text(_busy ? 'Stop' : 'Send')),
            ],
          ),
        ),
      ),
    ),
  );
}
