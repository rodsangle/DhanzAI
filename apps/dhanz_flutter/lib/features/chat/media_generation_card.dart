import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/providers.dart';
import '../creative/studio_screen.dart';
import 'chat_preview.dart';
import '../creative/creative_defaults.dart';

bool supportsVideoDuration(Map<String, dynamic> model, dynamic duration) {
  if (duration is! int) return false;
  final min = model['duration_min'] as int?;
  final max = model['duration_max'] as int?;
  if (min != null && max != null) {
    return duration >= min && duration <= max && (duration - min) % (model['duration_step'] as int? ?? 1) == 0;
  }
  return (model['durations'] as List).contains(duration);
}

/// Generation stays attached to the conversation; the server owns job execution.
class MediaGenerationCard extends ConsumerStatefulWidget {
  const MediaGenerationCard({required this.action, super.key});
  final Map<String, dynamic> action;

  @override
  ConsumerState<MediaGenerationCard> createState() => _MediaGenerationCardState();
}

class _MediaGenerationCardState extends ConsumerState<MediaGenerationCard> {
  Map<String, dynamic>? _job;
  String? _error;
  bool _busy = false;
  Timer? _poll;

  @override
  void initState() {
    super.initState();
    _busy = true;
    unawaited(_restore());
  }

  Future<void> _restore() async {
    try {
      final api = ref.read(apiClientProvider);
      final jobId = widget.action['job_id'] as String?;
      final job = jobId == null
          ? await api.creationForRequest(widget.action['request_key'] as String)
          : await api.creation(jobId);
      if (!mounted) return;
      setState(() => _job = job);
      if (job != null && ['queued', 'processing'].contains(job['status'])) {
        _poll = Timer.periodic(const Duration(seconds: 5), (_) => _refresh());
      }
    } on Object catch (e) {
      if (mounted) setState(() => _error = 'Could not restore generation: $e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  void dispose() {
    _poll?.cancel();
    super.dispose();
  }

  Future<void> _refresh() async {
    try {
      final job = await ref.read(apiClientProvider).creation(_job!['id'] as String);
      if (!mounted) return;
      setState(() {
        _job = job;
        _error = null;
      });
      if (!['queued', 'processing'].contains(job['status'])) _poll?.cancel();
    } on Object catch (e) {
      _poll?.cancel();
      if (mounted) setState(() => _error = 'Could not refresh: $e');
    }
  }

  Future<void> _generate() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final api = ref.read(apiClientProvider);
      final reviewedRequest = widget.action['generation_request'];
      if (reviewedRequest is Map) {
        final request = Map<String, dynamic>.from(reviewedRequest);
        final confirmed = await showDialog<bool>(
          context: context,
          builder: (context) => AlertDialog(
            title: const Text('Review generation cost'),
            content: Text(
              '${request['model']} · ${widget.action['cost_credits']} credits\n'
              '${request['ratio']}${request['kind'] == 'video' ? ' · ${request['duration']} seconds' : ''} · ${request['resolution']}\n'
              'Local generation can take many minutes or hours. Completion time is not guaranteed. '
              'Confirm you have rights and consent for this content.',
            ),
            actions: [
              TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
              FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Confirm and generate')),
            ],
          ),
        );
        if (confirmed != true || !mounted) return;
        final job = await api.generateMedia(request);
        if (!mounted) return;
        setState(() => _job = job);
        if (['queued', 'processing'].contains(job['status'])) {
          _poll = Timer.periodic(const Duration(seconds: 5), (_) => _refresh());
        }
        return;
      }
      final caps = await api.creativeCapabilities();
      final a = Map<String, dynamic>.from(widget.action);
      final video = a['kind'] == 'video';
      final compatible = (caps['models'] as List)
          .cast<Map<String, dynamic>>()
          .where(
            (m) =>
                m['kind'] == a['kind'] &&
                (m['ratios'] as List).contains(a['ratio']) &&
                (m['operations'] as List).contains('generate'),
          )
          .toList();
      if (video && compatible.isNotEmpty && !compatible.any((m) => supportsVideoDuration(m, a['duration']))) {
        final requested = a['duration'] as int;
        final lengths = compatible.expand((m) => (m['durations'] as List).cast<int>()).toSet().toList()..sort();
        if (lengths.isEmpty) throw StateError('The configured video models have no supported clip lengths.');
        if (!mounted) return;
        var chosen = lengths.reduce((x, y) => (x - requested).abs() <= (y - requested).abs() ? x : y);
        final duration = await showDialog<int>(
          context: context,
          builder: (context) => StatefulBuilder(
            builder: (context, update) => AlertDialog(
              title: const Text('Choose a supported clip length'),
              content: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(
                    'Your video models do not support $requested seconds. Choose a length to continue. The prompt will be updated after you confirm.',
                  ),
                  DropdownButton<int>(
                    isExpanded: true,
                    value: chosen,
                    items: [
                      for (final seconds in lengths)
                        DropdownMenuItem(
                          value: seconds,
                          child: Text(
                            seconds >= 60 && seconds % 60 == 0 ? '${seconds ~/ 60} minutes' : '$seconds seconds',
                          ),
                        ),
                    ],
                    onChanged: (value) {
                      if (value != null) update(() => chosen = value);
                    },
                  ),
                ],
              ),
              actions: [
                TextButton(onPressed: () => Navigator.pop(context), child: const Text('Keep original request')),
                FilledButton(onPressed: () => Navigator.pop(context, chosen), child: Text('Use $chosen seconds')),
              ],
            ),
          ),
        );
        if (duration == null || !mounted) return;
        var prompt = a['prompt'] as String;
        prompt = prompt.replaceAll(
          RegExp('\\b$requested(?:-|\\s+)(?:seconds?|secs?)\\b', caseSensitive: false),
          '$duration seconds',
        );
        if (requested % 60 == 0) {
          prompt = prompt.replaceAll(
            RegExp('\\b${requested ~/ 60}(?:-|\\s+)(?:minutes?|mins?)\\b', caseSensitive: false),
            '$duration seconds',
          );
        }
        a['prompt'] = 'Duration: $duration seconds.\n$prompt';
        a['duration'] = duration;
      }
      final models = creativeModelsByQuality(
        compatible.where((m) => !video || supportsVideoDuration(m, a['duration'])),
      );
      if (models.isEmpty) {
        throw StateError(
          'No configured ${a['kind']} model supports this ratio${video ? ' and exact clip length' : ''}. Adjust the request in chat.',
        );
      }
      final credits = await api.creativeCredits();
      if (!mounted) return;
      var selected = models.first;
      final confirmed = await showDialog<bool>(
        context: context,
        builder: (context) => StatefulBuilder(
          builder: (context, update) {
            final cost = selected['model'] == 'wan-longform-local' && selected['provider'] == 'local-diffusers'
                ? 0
                : video
                ? (credits['video_cost_per_second'] as num) * (a['duration'] as num)
                : credits['image_cost'];
            return AlertDialog(
              title: Text('Generate ${a['kind']}'),
              content: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  DropdownButton<String>(
                    isExpanded: true,
                    value: selected['model'] as String,
                    items: [
                      for (final m in models)
                        DropdownMenuItem(value: m['model'] as String, child: Text('${m['model']}')),
                    ],
                    onChanged: (value) => update(() => selected = models.firstWhere((m) => m['model'] == value)),
                  ),
                  Text(
                    '${a['ratio']}${video ? ' · ${a['duration']} seconds' : ''} · $cost credits\nConfirm you have rights and consent for this content.',
                  ),
                ],
              ),
              actions: [
                TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
                FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Generate')),
              ],
            );
          },
        ),
      );
      if (confirmed != true || !mounted) return;
      final qualities = selected['qualities'] as List;
      final job = await api.generateMedia({
        'request_key': a['request_key'],
        'kind': a['kind'],
        'model': selected['model'],
        'prompt': a['prompt'],
        'ratio': a['ratio'],
        'operation': 'generate',
        'format': video ? 'mp4' : (selected['formats'] as List).first,
        'quality': qualities.isEmpty ? 'medium' : qualities.first,
        'resolution': preferredCreativeResolution(selected) ?? '720p',
        if (video) 'duration': a['duration'],
        'rights_confirmed': true,
      });
      if (!mounted) return;
      setState(() => _job = job);
      if (['queued', 'processing'].contains(job['status'])) {
        _poll = Timer.periodic(const Duration(seconds: 5), (_) => _refresh());
      }
    } on Object catch (e) {
      if (mounted) setState(() => _error = '$e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final job = _job;
    final options = job?['options'] as Map?;
    final active = job != null && ['queued', 'processing'].contains(job['status']);
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('${widget.action['kind'] == 'video' ? 'Video' : 'Image'} · ${job?['status'] ?? 'Ready to generate'}'),
            if (job?['model'] != null) Text('${job!['model']} · ${job['cost']} credits'),
            if (options != null)
              Text(
                [
                  if (options['resolution'] != null) '${options['resolution']} export',
                  if (options['ratio'] != null) '${options['ratio']}',
                  if (widget.action['kind'] == 'video' && options['duration'] != null) '${options['duration']} seconds',
                ].join(' · '),
              ),
            Text('${job?['prompt'] ?? widget.action['prompt']}', maxLines: 4, overflow: TextOverflow.ellipsis),
            if (_error != null) Text(_error!),
            if (job?['error'] != null) Text('${job!['error']}'),
            if (active) const LinearProgressIndicator(),
            if (widget.action['automatic'] == true) const Text('Runs in the background. You can keep chatting.'),
            if (job == null && widget.action['automatic'] == true)
              TextButton(onPressed: _busy ? null : _restore, child: const Text('Refresh generation')),
            if (job == null && widget.action['automatic'] != true)
              FilledButton(
                onPressed: _busy ? null : _generate,
                child: Text(
                  _busy
                      ? 'Preparing…'
                      : widget.action['generation_request'] != null
                      ? 'Review generation'
                      : 'Generate here',
                ),
              ),
            if (job != null) TextButton(onPressed: _refresh, child: const Text('Refresh status')),
            if (active)
              TextButton(
                onPressed: () async {
                  try {
                    await ref.read(apiClientProvider).cancelCreation(job['id'] as String);
                    await _refresh();
                  } on Object catch (e) {
                    if (mounted) setState(() => _error = '$e');
                  }
                },
                child: const Text('Cancel generation'),
              ),
            if (job?['has_media'] == true)
              ActionChip(
                avatar: const Icon(Icons.visibility_outlined, size: 18),
                label: const Text('Preview'),
                tooltip: 'Preview and download this ${widget.action['kind'] == 'video' ? 'video' : 'image'}',
                onPressed: () => openCreationPreview(context, job!),
              ),
          ],
        ),
      ),
    );
  }
}

/// Opens a finished photo or video like a file preview: in the chat's side panel when there is one,
/// otherwise full size in a dialog.
void openCreationPreview(BuildContext context, Map<String, dynamic> job) {
  final panel = ChatPreviewScope.of(context);
  final kind = job['kind'] == 'video' ? 'Video' : 'Image';
  final prompt = '${job['prompt'] ?? ''}'.trim();
  final title = prompt.isEmpty ? kind : '$kind · ${prompt.length > 40 ? '${prompt.substring(0, 40)}…' : prompt}';
  if (panel != null) {
    panel.open(ChatPreviewTarget(documentId: 'creation:${job['id']}', filename: title, creation: job));
    return;
  }
  showDialog<void>(
    context: context,
    builder: (_) => Dialog(
      child: SizedBox(
        width: 900,
        height: MediaQuery.sizeOf(context).height * 0.85,
        child: CreationPreview(job: job),
      ),
    ),
  );
}
