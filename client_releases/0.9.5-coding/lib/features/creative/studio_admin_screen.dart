import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/providers.dart';
import 'studio_screen.dart';

class StudioAdminScreen extends ConsumerStatefulWidget {
  const StudioAdminScreen({super.key});

  @override
  ConsumerState<StudioAdminScreen> createState() => _StudioAdminScreenState();
}

class _StudioAdminScreenState extends ConsumerState<StudioAdminScreen> {
  final _image = TextEditingController();
  final _video = TextEditingController();
  final _allowance = TextEditingController();
  List<Map<String, dynamic>> _reports = [];
  String? _error;
  bool _busy = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _image.dispose();
    _video.dispose();
    _allowance.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    try {
      final api = ref.read(apiClientProvider);
      final results = await Future.wait([api.creativePolicy(), api.creativeReports()]);
      if (!mounted) return;
      final policy = results.first as Map<String, dynamic>;
      _image.text = '${policy['image_cost']}';
      _video.text = '${policy['video_cost_per_second']}';
      _allowance.text = '${policy['monthly_allowance']}';
      setState(() {
        _reports = results.last as List<Map<String, dynamic>>;
        _error = null;
      });
    } on Exception catch (error) {
      if (mounted) setState(() => _error = '$error');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _save() async {
    final image = int.tryParse(_image.text),
        video = int.tryParse(_video.text),
        allowance = int.tryParse(_allowance.text);
    if (image == null || image < 1 || video == null || video < 1 || allowance == null || allowance < 0) {
      setState(() => _error = 'Enter positive credit costs and a nonnegative monthly allowance.');
      return;
    }
    setState(() => _busy = true);
    try {
      await ref.read(apiClientProvider).updateCreativePolicy({
        'image_cost': image,
        'video_cost_per_second': video,
        'monthly_allowance': allowance,
      });
      ref.invalidate(studioProvider);
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Credit policy saved')));
      await _load();
    } on Exception catch (error) {
      if (mounted) setState(() => _error = '$error');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('Studio administration')),
    body: ListView(
      padding: const EdgeInsets.all(24),
      children: [
        if (_busy) const LinearProgressIndicator(),
        if (_error != null) Text(_error!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
        Text('Credit policy', style: Theme.of(context).textTheme.headlineSmall),
        const Text(
          'New jobs use current costs. Allowance changes apply on the next UTC calendar month. '
          'Purchased credits and account plans are administered through the secured server API.',
        ),
        const SizedBox(height: 16),
        for (final field in [
          ('Image generation cost', _image),
          ('Video cost per second', _video),
          ('Default monthly allowance', _allowance),
        ])
          Padding(
            padding: const EdgeInsets.only(bottom: 12),
            child: TextField(
              controller: field.$2,
              enabled: !_busy,
              keyboardType: TextInputType.number,
              decoration: InputDecoration(labelText: field.$1),
            ),
          ),
        FilledButton(onPressed: _busy ? null : _save, child: const Text('Save credit policy')),
        const SizedBox(height: 32),
        Text('Content reports', style: Theme.of(context).textTheme.headlineSmall),
        if (_reports.isEmpty) const Text('No reports.'),
        for (final report in _reports)
          Card(
            child: ListTile(
              title: Text('${report['reason']}'),
              subtitle: SelectableText('Creation ${report['job_id']}\nAccount ${report['user_id']}'),
              trailing: IconButton(
                tooltip: 'Remove reported creation',
                icon: const Icon(Icons.block),
                onPressed: _busy
                    ? null
                    : () async {
                        final confirmed = await showDialog<bool>(
                          context: context,
                          builder: (context) => AlertDialog(
                            title: const Text('Remove this creation?'),
                            content: const Text('This revokes its media links and schedules its files for deletion.'),
                            actions: [
                              TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Keep')),
                              FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Remove')),
                            ],
                          ),
                        );
                        if (confirmed != true || !mounted) return;
                        setState(() => _busy = true);
                        try {
                          await ref.read(apiClientProvider).removeUnsafeCreation(report['job_id'] as String);
                          ref.invalidate(studioProvider);
                          await _load();
                        } on Exception catch (error) {
                          if (mounted) setState(() => _error = '$error');
                        } finally {
                          if (mounted) setState(() => _busy = false);
                        }
                      },
              ),
            ),
          ),
      ],
    ),
  );
}
