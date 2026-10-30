import 'dart:async';
import 'dart:convert';
import 'dart:math';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:media_kit/media_kit.dart';
import 'package:media_kit_video/media_kit_video.dart';
import 'package:share_plus/share_plus.dart';

import '../../core/api/api_client.dart';
import '../../core/files.dart';
import '../../core/providers.dart';
import '../../widgets/text_prompt_dialog.dart';
import '../auth/auth_controller.dart';
import '../chat/chat_controller.dart';
import 'studio_admin_screen.dart';

typedef StudioData = ({
  List<Map<String, dynamic>> models,
  Map<String, dynamic> credits,
  List<Map<String, dynamic>> jobs,
});

final studioProvider = FutureProvider.autoDispose<StudioData>((ref) async {
  ref.watch(authControllerProvider.select((state) => state.value?.id));
  final api = ref.watch(apiClientProvider);
  final results = await Future.wait([api.creativeCapabilities(), api.creativeCredits(), api.creations()]);
  return (
    models: ((results[0] as Map<String, dynamic>)['models'] as List).cast<Map<String, dynamic>>(),
    credits: results[1] as Map<String, dynamic>,
    jobs: results[2] as List<Map<String, dynamic>>,
  );
});

class StudioScreen extends ConsumerStatefulWidget {
  const StudioScreen({super.key});

  @override
  ConsumerState<StudioScreen> createState() => _StudioScreenState();
}

class _StudioScreenState extends ConsumerState<StudioScreen> {
  Timer? _poll;

  @override
  void initState() {
    super.initState();
    _poll = Timer.periodic(const Duration(seconds: 5), (_) {
      final data = ref.read(studioProvider).value;
      if (data?.jobs.any((job) => ['queued', 'processing'].contains(job['status'])) == true) {
        ref.invalidate(studioProvider);
      }
    });
  }

  @override
  void dispose() {
    _poll?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(studioProvider);
    return DefaultTabController(
      length: 3,
      child: Scaffold(
        appBar: AppBar(
          leading: IconButton(icon: const Icon(Icons.arrow_back), onPressed: () => context.go('/chat')),
          title: const Text('DHANZ Creative Studio'),
          actions: [
            if (ref.watch(authControllerProvider).value?.isAdmin == true)
              IconButton(
                tooltip: 'Studio administration',
                icon: const Icon(Icons.admin_panel_settings_outlined),
                onPressed: () =>
                    Navigator.of(context).push(MaterialPageRoute<void>(builder: (_) => const StudioAdminScreen())),
              ),
            IconButton(
              tooltip: 'Refresh creations',
              onPressed: () => ref.invalidate(studioProvider),
              icon: const Icon(Icons.refresh),
            ),
          ],
          bottom: const TabBar(
            tabs: [
              Tab(text: 'AI Images'),
              Tab(text: 'AI Videos'),
              Tab(text: 'My Creations'),
            ],
          ),
        ),
        body: state.when(
          loading: () => const Center(child: CircularProgressIndicator()),
          error: (error, _) => Center(
            child: Padding(
              padding: const EdgeInsets.all(24),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text('$error'),
                  TextButton(onPressed: () => ref.invalidate(studioProvider), child: const Text('Retry')),
                ],
              ),
            ),
          ),
          data: (data) => Column(
            children: [
              Padding(
                padding: const EdgeInsets.all(12),
                child: Text(
                  '${data.credits['balance']} credits available · ${data.credits['reserved']} reserved · '
                  '${data.credits['consumed']} used · ${data.credits['monthly_allowance']} monthly allowance',
                ),
              ),
              Expanded(
                child: TabBarView(
                  children: [
                    _GenerationForm(key: const ValueKey('image-form'), kind: 'image', data: data),
                    _GenerationForm(key: const ValueKey('video-form'), kind: 'video', data: data),
                    _Gallery(jobs: data.jobs),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _GenerationForm extends ConsumerStatefulWidget {
  const _GenerationForm({super.key, required this.kind, required this.data});
  final String kind;
  final StudioData data;

  @override
  ConsumerState<_GenerationForm> createState() => _GenerationFormState();
}

class _GenerationFormState extends ConsumerState<_GenerationForm> with AutomaticKeepAliveClientMixin {
  final _prompt = TextEditingController();
  String? _model, _ratio, _quality, _format, _operation, _resolution;
  int? _duration;
  String? _referenceId, _referenceName, _error, _pendingKey, _pendingFingerprint;
  bool _rights = false, _busy = false;

  @override
  bool get wantKeepAlive => true;

  @override
  void dispose() {
    _prompt.dispose();
    super.dispose();
  }

  Future<void> _reference() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final files = await pickFiles();
      if (files.isEmpty) return;
      final file = files.first;
      if (file.bytes.length > 8 * 1024 * 1024 ||
          !RegExp(r'\.(png|jpe?g|webp)$', caseSensitive: false).hasMatch(file.name)) {
        throw ApiException(422, 'Choose a PNG, JPEG or WebP image up to 8 MB.');
      }
      final doc = await ref.read(apiClientProvider).uploadFile(file.name, file.bytes);
      if (!mounted) return;
      if (doc.fileType != 'image') throw ApiException(422, 'Choose an image file.');
      setState(() {
        _referenceId = doc.id;
        _referenceName = doc.title;
      });
    } on Exception catch (error) {
      if (mounted) setState(() => _error = '$error');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _generate(Map<String, dynamic> model) async {
    if (_busy) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    final body = <String, dynamic>{
      'kind': widget.kind,
      'model': model['model'],
      'prompt': _prompt.text.trim(),
      'ratio': _ratio,
      'quality': _quality ?? 'medium',
      'format': _format,
      'operation': _operation ?? 'generate',
      'duration': _duration ?? 5,
      'resolution': _resolution ?? '720p',
      'reference_id': _referenceId,
      'rights_confirmed': _rights,
    };
    final fingerprint = jsonEncode(body);
    if (_pendingKey == null || fingerprint != _pendingFingerprint) {
      _pendingKey = '${DateTime.now().microsecondsSinceEpoch}_${Random.secure().nextInt(1 << 32)}';
      _pendingFingerprint = fingerprint;
    }
    body['request_key'] = _pendingKey;
    try {
      await ref.read(apiClientProvider).generateMedia(body);
      _pendingKey = null;
      if (!mounted) return;
      ref.invalidate(studioProvider);
      DefaultTabController.of(context).animateTo(2);
    } on Exception catch (error) {
      if (mounted) setState(() => _error = '$error');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Widget _choice(String label, List<dynamic> options, String? value, ValueChanged<String> change) => SizedBox(
    width: 220,
    child: DropdownButtonFormField<String>(
      key: ValueKey('$label-$value'),
      initialValue: value,
      isExpanded: true,
      decoration: InputDecoration(labelText: label),
      items: [
        for (final option in options) DropdownMenuItem(value: '$option', child: Text('$option'.replaceAll('_', ' '))),
      ],
      onChanged: _busy
          ? null
          : (value) {
              if (value != null) setState(() => change(value));
            },
    ),
  );

  @override
  Widget build(BuildContext context) {
    super.build(context);
    final models = widget.data.models.where((model) => model['kind'] == widget.kind).toList();
    if (models.isEmpty) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(32),
          child: Text(
            '${widget.kind == 'image' ? 'Image' : 'Video'} generation is not configured on this server. '
            'An administrator must enable a provider and content moderation.',
          ),
        ),
      );
    }
    final model = models.firstWhere((m) => m['model'] == _model, orElse: () => models.first);
    _model = model['model'] as String;
    final ratios = model['ratios'] as List;
    if (!ratios.contains(_ratio)) _ratio = '${ratios.first}';
    final formats = model['formats'] as List;
    if (!formats.contains(_format)) _format = '${formats.first}';
    final qualities = model['qualities'] as List;
    if (qualities.isNotEmpty && !qualities.contains(_quality)) _quality = '${qualities.first}';
    final operations = model['operations'] as List;
    if (!operations.contains(_operation)) _operation = '${operations.first}';
    final durations = model['durations'] as List;
    if (durations.isNotEmpty && !durations.contains(_duration)) _duration = durations.first as int;
    final resolutions = model['resolutions'] as List;
    if (resolutions.isNotEmpty && !resolutions.contains(_resolution)) _resolution = '${resolutions.first}';
    final cost = widget.kind == 'image'
        ? widget.data.credits['image_cost'] as int
        : (widget.data.credits['video_cost_per_second'] as int) * (_duration ?? 5);
    return SingleChildScrollView(
      padding: const EdgeInsets.all(24),
      child: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 850),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text(
                widget.kind == 'image' ? 'Imagine it. Create it.' : 'Bring your ideas to life.',
                style: Theme.of(context).textTheme.headlineMedium,
              ),
              const SizedBox(height: 8),
              const Text(
                'Private to your account. Prompts and references are sent to the selected generation provider '
                'and OpenAI safety screening. Review AI-generated media before sharing.',
              ),
              const SizedBox(height: 24),
              TextField(
                controller: _prompt,
                enabled: !_busy,
                maxLength: 4000,
                minLines: 5,
                maxLines: 9,
                decoration: InputDecoration(
                  labelText: '${widget.kind == 'image' ? 'Image' : 'Video'} prompt',
                  hintText: 'Describe your subject, setting, lighting, style and composition…',
                  border: const OutlineInputBorder(),
                ),
              ),
              Align(
                alignment: Alignment.centerLeft,
                child: TextButton.icon(
                  icon: const Icon(Icons.chat_bubble_outline),
                  label: const Text('Ask Dhanz to improve this prompt'),
                  onPressed: _busy
                      ? null
                      : () {
                          final prompt =
                              'Help me improve this ${widget.kind} generation prompt. '
                              'Return a polished prompt and explain your suggestions:\n${_prompt.text}';
                          context.go('/chat');
                          unawaited(ref.read(chatControllerProvider.notifier).send(prompt));
                        },
                ),
              ),
              const SizedBox(height: 12),
              Wrap(
                spacing: 16,
                runSpacing: 16,
                children: [
                  _choice('AI model', [for (final m in models) m['model']], _model, (v) => _model = v),
                  _choice('Aspect ratio', ratios, _ratio, (v) => _ratio = v),
                  if (qualities.isNotEmpty) _choice('Quality', qualities, _quality, (v) => _quality = v),
                  _choice('File format', formats, _format, (v) => _format = v),
                  if (operations.length > 1) _choice('Operation', operations, _operation, (v) => _operation = v),
                  if (durations.isNotEmpty)
                    _choice('Duration (seconds)', durations, '$_duration', (v) => _duration = int.parse(v)),
                  if (resolutions.isNotEmpty) _choice('Resolution', resolutions, _resolution, (v) => _resolution = v),
                ],
              ),
              const SizedBox(height: 20),
              if (model['reference'] == true)
                Wrap(
                  spacing: 12,
                  crossAxisAlignment: WrapCrossAlignment.center,
                  children: [
                    OutlinedButton.icon(
                      onPressed: _busy ? null : _reference,
                      icon: const Icon(Icons.add_photo_alternate_outlined),
                      label: const Text('Upload reference image'),
                    ),
                    if (_referenceName != null)
                      InputChip(
                        label: Text(_referenceName!),
                        onDeleted: _busy
                            ? null
                            : () => setState(() {
                                _referenceId = null;
                                _referenceName = null;
                              }),
                      ),
                  ],
                ),
              const Text('References are also saved in your private Knowledge library, where you can delete them.'),
              CheckboxListTile(
                contentPadding: EdgeInsets.zero,
                value: _rights,
                onChanged: _busy ? null : (value) => setState(() => _rights = value ?? false),
                title: const Text('I have the rights and consent to use this content.'),
                subtitle: const Text('No nonconsensual intimate content, deceptive impersonation, or infringement.'),
              ),
              if (_error != null)
                Padding(
                  padding: const EdgeInsets.only(bottom: 12),
                  child: Text(_error!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
                ),
              FilledButton.icon(
                onPressed: !_busy && _rights ? () => _generate(model) : null,
                icon: _busy
                    ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2))
                    : const Icon(Icons.auto_awesome),
                label: Text('Generate · $cost credits'),
              ),
              const SizedBox(height: 12),
              const Text(
                'Credits are reserved when queued and released for failed or canceled jobs. '
                'You can leave this screen and return to My Creations.',
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _Gallery extends ConsumerStatefulWidget {
  const _Gallery({required this.jobs});
  final List<Map<String, dynamic>> jobs;

  @override
  ConsumerState<_Gallery> createState() => _GalleryState();
}

class _GalleryState extends ConsumerState<_Gallery> {
  final _older = <Map<String, dynamic>>[];
  bool _loadingMore = false, _lastPage = false;

  @override
  void didUpdateWidget(covariant _Gallery oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.jobs.firstOrNull?['id'] != widget.jobs.firstOrNull?['id']) {
      _older.clear();
      _lastPage = false;
    }
  }

  Future<void> _action(BuildContext context, WidgetRef ref, Future<void> Function() action) async {
    try {
      await action();
      ref.invalidate(studioProvider);
    } on Exception catch (error) {
      if (context.mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('$error')));
    }
  }

  @override
  Widget build(BuildContext context) {
    final jobs = [...widget.jobs, ..._older];
    if (jobs.isEmpty) return const Center(child: Text('Your creations will appear here.'));
    return ListView.builder(
      padding: const EdgeInsets.all(20),
      itemCount: jobs.length + 1,
      itemBuilder: (context, index) {
        if (index == jobs.length) {
          if (_lastPage || widget.jobs.length < 30) return const SizedBox(height: 20);
          return TextButton(
            onPressed: _loadingMore
                ? null
                : () async {
                    setState(() => _loadingMore = true);
                    await _action(context, ref, () async {
                      final more = await ref.read(apiClientProvider).creations(offset: jobs.length);
                      if (mounted) {
                        setState(() {
                          _older.addAll(more);
                          _lastPage = more.length < 30;
                        });
                      }
                    });
                    if (mounted) setState(() => _loadingMore = false);
                  },
            child: Text(_loadingMore ? 'Loading…' : 'Load older creations'),
          );
        }
        final job = jobs[index];
        final active = ['queued', 'processing'].contains(job['status']);
        return Card(
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Icon(job['kind'] == 'image' ? Icons.image_outlined : Icons.movie_outlined),
                    const SizedBox(width: 12),
                    Expanded(child: Text('${job['model']} · ${job['status']} · ${job['cost']} credits')),
                  ],
                ),
                const SizedBox(height: 8),
                Text('${job['prompt']}', maxLines: 3, overflow: TextOverflow.ellipsis),
                if (active)
                  Padding(
                    padding: const EdgeInsets.symmetric(vertical: 12),
                    child: LinearProgressIndicator(
                      value: job['status'] == 'queued' ? null : (job['progress'] as num) / 100,
                    ),
                  ),
                if (job['error'] != null) Text('${job['error']}'),
                Wrap(
                  spacing: 8,
                  children: [
                    if (job['has_media'] == true)
                      FilledButton.tonalIcon(
                        icon: const Icon(Icons.play_arrow),
                        label: const Text('Preview / download'),
                        onPressed: () =>
                            Navigator.of(context)
                                .push(MaterialPageRoute<void>(builder: (_) => _CreationPreview(job: job))),
                      ),
                    if (active)
                      TextButton(
                        onPressed: () => _action(
                          context,
                          ref,
                          () => ref.read(apiClientProvider).cancelCreation(job['id'] as String),
                        ),
                        child: const Text('Cancel generation'),
                      ),
                    if (!active)
                      TextButton(
                        onPressed: () => _action(context, ref, () async {
                          final confirmed = await showDialog<bool>(
                            context: context,
                            builder: (context) => AlertDialog(
                              title: const Text('Delete this creation?'),
                              content: const Text('Its media will be removed from your account.'),
                              actions: [
                                TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Keep')),
                                FilledButton(
                                  onPressed: () => Navigator.pop(context, true),
                                  child: const Text('Delete'),
                                ),
                              ],
                            ),
                          );
                          if (confirmed == true) await ref.read(apiClientProvider).deleteCreation(job['id'] as String);
                        }),
                        child: const Text('Delete'),
                      ),
                    TextButton(
                      onPressed: () => _action(context, ref, () async {
                        final reason = await showTextPrompt(
                          context,
                          title: 'Report unsafe content',
                          confirmLabel: 'Submit',
                          maxLength: 1000,
                        );
                        if (reason != null) {
                          await ref.read(apiClientProvider).reportCreation(job['id'] as String, reason);
                        }
                      }),
                      child: const Text('Report'),
                    ),
                    TextButton(
                      onPressed: () async {
                        final body = Map<String, dynamic>.from(job['options'] as Map);
                        final consent = await showDialog<bool>(
                          context: context,
                          builder: (context) => AlertDialog(
                            title: const Text('Generate another variation?'),
                            content: Text(
                              'This creates a new job and reserves ${job['cost']} credits at the current rate. '
                              'Confirm that you have rights and consent for this content. Variations use the same prompt without a reference.',
                            ),
                            actions: [
                              TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
                              FilledButton(
                                onPressed: () => Navigator.pop(context, true),
                                child: const Text('Generate'),
                              ),
                            ],
                          ),
                        );
                        if (consent != true || !context.mounted) return;
                        await _action(context, ref, () async {
                          await ref.read(apiClientProvider).generateMedia({
                            ...body,
                            'kind': job['kind'],
                            'model': job['model'],
                            'prompt': job['prompt'],
                            'operation': 'generate',
                            'rights_confirmed': true,
                            'request_key':
                                '${DateTime.now().microsecondsSinceEpoch}_${Random.secure().nextInt(1 << 32)}',
                          });
                        });
                      },
                      child: const Text('Generate variation'),
                    ),
                  ],
                ),
              ],
            ),
          ),
        );
      },
    );
  }
}

class _CreationPreview extends ConsumerStatefulWidget {
  const _CreationPreview({required this.job});
  final Map<String, dynamic> job;

  @override
  ConsumerState<_CreationPreview> createState() => _CreationPreviewState();
}

class _CreationPreviewState extends ConsumerState<_CreationPreview> {
  Uint8List? _image;
  Player? _player;
  VideoController? _video;
  String? _error;
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  Future<void> _load() async {
    try {
      final api = ref.read(apiClientProvider);
      if (widget.job['kind'] == 'image') {
        final data = await api.downloadCreation(widget.job['id'] as String);
        if (mounted) setState(() => _image = data);
      } else {
        final url = await api.creationMediaUrl(widget.job['id'] as String);
        if (!mounted) return;
        MediaKit.ensureInitialized();
        _player = Player();
        _video = VideoController(_player!);
        await _player!.open(Media(url), play: false);
        if (mounted) setState(() {});
      }
    } on Object catch (error) {
      if (mounted) setState(() => _error = 'Preview unavailable: $error');
    }
  }

  @override
  void dispose() {
    unawaited(_player?.dispose());
    super.dispose();
  }

  Future<void> _save(bool share) async {
    final box = context.findRenderObject() as RenderBox?;
    final origin = box == null ? null : box.localToGlobal(Offset.zero) & box.size;
    setState(() => _busy = true);
    try {
      final bytes = _image ?? await ref.read(apiClientProvider).downloadCreation(widget.job['id'] as String);
      final format = (widget.job['options'] as Map)['format'] as String;
      final mime = widget.job['kind'] == 'image' ? 'image/$format' : 'video/mp4';
      final name = 'dhanz-${widget.job['id']}.$format';
      if (share) {
        await SharePlus.instance.share(
          ShareParams(
            files: [XFile.fromData(bytes, mimeType: mime)],
            fileNameOverrides: [name],
            subject: 'Created with DHANZ AI',
            sharePositionOrigin: origin,
          ),
        );
      } else {
        await saveBytes(name, bytes, mimeType: mime);
      }
    } on Exception catch (error) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('$error')));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('Your creation')),
    body: Column(
      children: [
        Expanded(
          child: Center(
            child: _error != null
                ? Text(_error!)
                : _image != null
                ? InteractiveViewer(child: Image.memory(_image!, fit: BoxFit.contain))
                : _video != null
                ? Video(controller: _video!)
                : const CircularProgressIndicator(),
          ),
        ),
        const Padding(padding: EdgeInsets.all(8), child: Text('AI-generated · Private to your account')),
        Padding(
          padding: const EdgeInsets.all(16),
          child: Wrap(
            spacing: 12,
            children: [
              FilledButton.icon(
                onPressed: _busy ? null : () => _save(false),
                icon: const Icon(Icons.download),
                label: const Text('Download'),
              ),
              OutlinedButton.icon(
                onPressed: _busy ? null : () => _save(true),
                icon: const Icon(Icons.share),
                label: const Text('Share…'),
              ),
            ],
          ),
        ),
      ],
    ),
  );
}
