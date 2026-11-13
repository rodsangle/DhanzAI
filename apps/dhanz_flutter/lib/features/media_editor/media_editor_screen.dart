import 'dart:async';
import 'dart:convert';
import 'dart:math';
import 'dart:typed_data';

import 'package:crypto/crypto.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:media_kit/media_kit.dart';
import 'package:media_kit_video/media_kit_video.dart';

import '../../core/api/api_client.dart';
import '../../core/files.dart';
import '../../core/providers.dart';
import 'blob_url.dart';

class MediaEditorScreen extends ConsumerStatefulWidget {
  const MediaEditorScreen({super.key});
  @override
  ConsumerState<MediaEditorScreen> createState() => _MediaEditorScreenState();
}

class _MediaEditorScreenState extends ConsumerState<MediaEditorScreen> {
  final _script = TextEditingController();
  final _start = TextEditingController(text: '0');
  final _duration = TextEditingController(text: '15');
  PickedFile? _video, _audio;
  String _mode = 'video', _voice = 'en-us', _effect = 'none';
  double _originalVolume = 1, _musicVolume = 0.25, _speed = 165;
  bool _busy = false;
  String? _error, _key, _fingerprint;
  List<Map<String, dynamic>> _jobs = [];
  Timer? _poll;
  @override
  void initState() {
    super.initState();
    unawaited(_load());
    _poll = Timer.periodic(const Duration(seconds: 4), (_) => _load());
  }

  Future<void> _load() async {
    try {
      final jobs = await ref.read(apiClientProvider).mediaJobs();
      if (mounted) setState(() => _jobs = jobs);
    } on Object catch (e) {
      if (mounted) {
        setState(
          () => _error = e is ApiException && e.statusCode == 404
              ? 'Install the Media editor server update first.'
              : '$e',
        );
      }
    }
  }

  Future<void> _pick(bool video) async {
    final files = await pickFiles();
    if (!mounted || files.isEmpty) return;
    if (files.first.bytes.length > 100 * 1024 * 1024) {
      setState(() => _error = 'Choose a file at most 100 MB.');
      return;
    }
    setState(() {
      if (video) {
        _video = files.first;
      } else {
        _audio = files.first;
      }
      _error = null;
    });
  }

  Future<void> _render() async {
    if (_busy) return;
    final start = double.tryParse(_start.text), duration = double.tryParse(_duration.text);
    if (start == null ||
        !start.isFinite ||
        start < 0 ||
        duration == null ||
        !duration.isFinite ||
        duration < 1 ||
        duration > 60) {
      setState(() => _error = 'Use a start of 0 or more and a duration of 1–60 seconds.');
      return;
    }
    if (_mode == 'video' && _video == null) {
      setState(() => _error = 'Choose a video first.');
      return;
    }
    final options = <String, dynamic>{
      'mode': _mode,
      'start': start,
      'duration': duration,
      'original_volume': _originalVolume,
      'music_volume': _musicVolume,
      'narration': _script.text,
      'voice': _voice,
      'speed': _speed.round(),
      'effect': _effect,
    };
    final signature = jsonEncode([
      options,
      _video == null ? null : sha256.convert(_video!.bytes).toString(),
      _audio == null ? null : sha256.convert(_audio!.bytes).toString(),
    ]);
    if (_fingerprint != signature) {
      _fingerprint = signature;
      _key = 'media_${DateTime.now().microsecondsSinceEpoch}_${Random.secure().nextInt(1 << 30)}';
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await ref
          .read(apiClientProvider)
          .renderMedia(
            options,
            _key!,
            video: _mode == 'video' ? _video : null,
            audio: _mode == 'video' ? _audio : null,
          );
      if (!mounted) return;
      _key = null;
      _fingerprint = null;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Export queued. You can switch chats; rendering continues on the server.')),
      );
      await _load();
    } on Object catch (e) {
      if (mounted) setState(() => _error = '$e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _download(Map<String, dynamic> job, {bool preview = false}) async {
    try {
      final data = await ref.read(apiClientProvider).downloadMediaJob(job['id'] as String);
      final name = job['filename'] as String;
      final mime = name.endsWith('.mp4') ? 'video/mp4' : 'audio/wav';
      if (preview) {
        if (!mounted) return;
        await showDialog<void>(
          context: context,
          builder: (_) => _MediaPreview(bytes: data, mime: mime),
        );
      } else {
        await saveBytes(name, data, mimeType: mime);
      }
    } on Object catch (e) {
      if (mounted) setState(() => _error = '$e');
    }
  }

  Future<void> _delete(String id) async {
    try {
      await ref.read(apiClientProvider).deleteMediaJob(id);
      await _load();
    } on Object catch (e) {
      if (mounted) setState(() => _error = '$e');
    }
  }

  @override
  void dispose() {
    _poll?.cancel();
    _script.dispose();
    _start.dispose();
    _duration.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(
      title: const Text('Media editor'),
      leading: IconButton(
        tooltip: 'Back to chat',
        icon: const Icon(Icons.arrow_back),
        onPressed: () => context.go('/chat'),
      ),
      actions: [IconButton(tooltip: 'Refresh exports', onPressed: _load, icon: const Icon(Icons.refresh))],
    ),
    body: Center(
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 1000),
        child: ListView(
          padding: const EdgeInsets.all(20),
          children: [
            const Text(
              'Edit existing video • Narration • Sound effects',
              style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold),
            ),
            const Text(
              'Local CPU rendering, no media API credits. MP4 exports up to 60 seconds / 720p. Narration uses a synthetic eSpeak NG voice. Exports and source files are kept for 7 days; download what you want to keep.',
            ),
            const SizedBox(height: 16),
            DropdownButtonFormField<String>(
              initialValue: _mode,
              decoration: const InputDecoration(labelText: 'Create'),
              items: const [
                DropdownMenuItem(value: 'video', child: Text('Edit a video')),
                DropdownMenuItem(value: 'narration', child: Text('Download narration (WAV)')),
                DropdownMenuItem(value: 'sound', child: Text('Create sound effect (WAV)')),
              ],
              onChanged: _busy ? null : (v) => setState(() => _mode = v!),
            ),
            if (_mode == 'video') ...[
              const SizedBox(height: 12),
              Wrap(
                spacing: 12,
                runSpacing: 8,
                children: [
                  OutlinedButton.icon(
                    onPressed: _busy ? null : () => _pick(true),
                    icon: const Icon(Icons.video_file),
                    label: Text(_video?.name ?? 'Choose video (up to 100 MB)'),
                  ),
                  OutlinedButton.icon(
                    onPressed: _busy ? null : () => _pick(false),
                    icon: const Icon(Icons.audio_file),
                    label: Text(_audio?.name ?? 'Add soundtrack'),
                  ),
                  if (_audio != null)
                    TextButton(
                      onPressed: _busy ? null : () => setState(() => _audio = null),
                      child: const Text('Remove soundtrack'),
                    ),
                ],
              ),
              const SizedBox(height: 12),
              TextField(
                controller: _start,
                keyboardType: TextInputType.number,
                decoration: const InputDecoration(labelText: 'Trim start (seconds)'),
              ),
              Text('Original audio: ${(_originalVolume * 100).round()}% (0 mutes it)'),
              Slider(
                value: _originalVolume,
                max: 2,
                divisions: 20,
                onChanged: _busy ? null : (v) => setState(() => _originalVolume = v),
              ),
              Text('Soundtrack volume: ${(_musicVolume * 100).round()}%'),
              Slider(
                value: _musicVolume,
                divisions: 20,
                onChanged: _busy ? null : (v) => setState(() => _musicVolume = v),
              ),
            ],
            if (_mode != 'narration')
              TextField(
                controller: _duration,
                keyboardType: TextInputType.number,
                decoration: const InputDecoration(labelText: 'Export duration (1–60 seconds)'),
              ),
            if (_mode != 'sound') ...[
              const SizedBox(height: 12),
              TextField(
                controller: _script,
                maxLines: 5,
                maxLength: 1500,
                decoration: InputDecoration(
                  labelText: _mode == 'video' ? 'Narration script (optional, must fit the clip)' : 'Narration script',
                ),
              ),
              DropdownButtonFormField<String>(
                initialValue: _voice,
                decoration: const InputDecoration(labelText: 'Narration language'),
                items: const [
                  DropdownMenuItem(value: 'en-us', child: Text('English (US)')),
                  DropdownMenuItem(value: 'en-gb', child: Text('English (UK)')),
                  DropdownMenuItem(value: 'es', child: Text('Spanish')),
                  DropdownMenuItem(value: 'fr', child: Text('French')),
                  DropdownMenuItem(value: 'de', child: Text('German')),
                ],
                onChanged: _busy ? null : (v) => setState(() => _voice = v!),
              ),
              Text('Narration speed: ${_speed.round()} words/minute'),
              Slider(
                value: _speed,
                min: 100,
                max: 230,
                divisions: 26,
                onChanged: _busy ? null : (v) => setState(() => _speed = v),
              ),
            ],
            if (_mode != 'narration')
              DropdownButtonFormField<String>(
                initialValue: _effect,
                decoration: const InputDecoration(labelText: 'Generated sound effect (at start)'),
                items: const [
                  DropdownMenuItem(value: 'none', child: Text('None')),
                  DropdownMenuItem(value: 'chime', child: Text('Chime')),
                  DropdownMenuItem(value: 'beep', child: Text('Beep')),
                  DropdownMenuItem(value: 'soft_tone', child: Text('Soft tone')),
                ],
                onChanged: _busy ? null : (v) => setState(() => _effect = v!),
              ),
            const SizedBox(height: 16),
            FilledButton.icon(
              onPressed: _busy ? null : _render,
              icon: const Icon(Icons.movie_creation_outlined),
              label: Text(_busy ? 'Uploading…' : 'Create export'),
            ),
            if (_error != null) SelectableText(_error!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
            const Divider(height: 32),
            const Text('Your exports', style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold)),
            if (_jobs.isEmpty) const Text('No exports yet.'),
            for (final job in _jobs)
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(12),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('${job['filename'] ?? job['mode']} · ${job['status']}'),
                      if ((job['source_name'] as String? ?? '').isNotEmpty) Text(job['source_name'] as String),
                      if (job['error'] != null) Text(job['error'] as String),
                      Wrap(
                        spacing: 8,
                        children: [
                          if (job['status'] == 'complete') ...[
                            TextButton.icon(
                              onPressed: () => _download(job, preview: true),
                              icon: const Icon(Icons.play_circle_outline),
                              label: const Text('Preview'),
                            ),
                            TextButton.icon(
                              onPressed: () => _download(job),
                              icon: const Icon(Icons.download),
                              label: const Text('Download'),
                            ),
                          ],
                          TextButton(onPressed: () => _delete(job['id'] as String), child: const Text('Delete')),
                        ],
                      ),
                    ],
                  ),
                ),
              ),
          ],
        ),
      ),
    ),
  );
}

class _MediaPreview extends StatefulWidget {
  const _MediaPreview({required this.bytes, required this.mime});
  final List<int> bytes;
  final String mime;
  @override
  State<_MediaPreview> createState() => _MediaPreviewState();
}

class _MediaPreviewState extends State<_MediaPreview> {
  late final Player _player;
  late final VideoController _video;
  late final String _url;
  String? _error;
  @override
  void initState() {
    super.initState();
    MediaKit.ensureInitialized();
    _player = Player();
    _video = VideoController(_player);
    _url = mediaObjectUrl(Uint8List.fromList(widget.bytes), widget.mime);
    unawaited(
      _player.open(Media(_url), play: false).catchError((Object e) {
        if (mounted) setState(() => _error = 'Preview unavailable. Download the file to play it.');
      }),
    );
  }

  @override
  void dispose() {
    unawaited(_player.dispose());
    revokeMediaObjectUrl(_url);
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
    title: const Text('Export preview'),
    content: SizedBox(
      width: 640,
      height: widget.mime == 'video/mp4' ? 360 : 100,
      child: _error != null
          ? Text(_error!)
          : widget.mime == 'video/mp4'
          ? Video(controller: _video)
          : Center(
              child: StreamBuilder<bool>(
                stream: _player.stream.playing,
                initialData: false,
                builder: (_, snapshot) => IconButton(
                  tooltip: snapshot.data! ? 'Pause' : 'Play narration or sound',
                  icon: Icon(snapshot.data! ? Icons.pause : Icons.play_arrow),
                  onPressed: _player.playOrPause,
                ),
              ),
            ),
    ),
    actions: [TextButton(onPressed: () => Navigator.pop(context), child: const Text('Close'))],
  );
}
