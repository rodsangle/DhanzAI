import 'dart:math';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../core/api/api_client.dart';
import '../../core/providers.dart';

Uri? integrationSignInUri(String value) {
  final uri = Uri.tryParse(value);
  if (uri == null || uri.scheme != 'https' || uri.userInfo.isNotEmpty || uri.port != 443 ||
      !{'login.microsoftonline.com', 'accounts.google.com'}.contains(uri.host)) {
    return null;
  }
  return uri;
}

String integrationRequestKey() {
  final random = Random.secure();
  return List.generate(32, (_) => random.nextInt(16).toRadixString(16)).join();
}

class IntegrationsScreen extends ConsumerStatefulWidget {
  const IntegrationsScreen({super.key});
  @override
  ConsumerState<IntegrationsScreen> createState() => _IntegrationsScreenState();
}

class _IntegrationsScreenState extends ConsumerState<IntegrationsScreen> {
  List<Map<String, dynamic>> _connections = [];
  final Map<String, Set<String>> _services = {};
  final Map<String, Uri> _pending = {};
  bool _busy = false;
  String? _error;
  ApiClient get _api => ref.read(apiClientProvider);

  @override
  void initState() {
    super.initState();
    Future.microtask(_load);
  }

  Future<void> _guard(Future<void> Function() action) async {
    if (_busy) return;
    setState(() { _busy = true; _error = null; });
    try {
      await action();
    } on ApiException catch (e) {
      if (mounted) {
        setState(() => _error = e.statusCode == 404
            ? 'The integrations server update is needed before connecting accounts.' : e.message);
      }
    } catch (_) {
      if (mounted) setState(() => _error = 'The connection could not complete. Refresh and check its status.');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _load() => _guard(() async {
    final data = await _api.integrations();
    if (!mounted) return;
    setState(() {
      _connections = (data['connections'] as List? ?? []).cast<Map<String, dynamic>>();
      for (final item in _connections) {
        final name = item['provider'] as String;
        _services.putIfAbsent(name, () => item['connected'] == true
            ? (item['services'] as List).cast<String>().toSet() : {'files', 'mail'});
        if (item['connected'] == true) _pending.remove(name);
      }
    });
  });

  void _notice(String text) {
    if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(text)));
  }

  Future<void> _connect(String name) => _guard(() async {
    final result = await _api.integrationConnect(name, _services[name]!.toList());
    final uri = integrationSignInUri(result['authorization_url'] as String? ?? '');
    if (uri == null) throw const FormatException('Invalid provider sign-in address');
    if (mounted) setState(() => _pending[name] = uri);
  });

  Future<void> _disconnect(String name) async {
    await _guard(() async {
      await _api.integrationDisconnect(name);
      _notice('Disconnected from Dhanz. You can also remove app consent in your provider’s account settings.');
    });
    if (mounted) await _load();
  }

  Future<void> _files(String name) async {
    List<Map<String, dynamic>> rows = [];
    var searching = false;
    final query = TextEditingController();
    await _guard(() async {
      final data = await _api.integrationOperation(name, {'operation': 'files'});
      rows = (data['files'] as List).cast<Map<String, dynamic>>();
    });
    if (!mounted || _error != null) { query.dispose(); return; }
    final selected = await showDialog<Map<String, dynamic>>(
      context: context,
      builder: (dialogContext) => StatefulBuilder(builder: (context, update) {
        return AlertDialog(
          title: const Text('Import a cloud file'),
          content: SizedBox(width: 560, height: 430, child: Column(children: [
            TextField(controller: query, decoration: InputDecoration(labelText: 'Search filename', suffixIcon: IconButton(
              tooltip: 'Search', icon: const Icon(Icons.search), onPressed: searching ? null : () async {
                update(() => searching = true);
                try {
                  final data = await _api.integrationOperation(name, {'operation': 'files', 'query': query.text});
                  if (context.mounted) update(() => rows = (data['files'] as List).cast<Map<String, dynamic>>());
                } on ApiException catch (e) { _notice(e.message); }
                finally { if (context.mounted) update(() => searching = false); }
              },
            ))),
            const Text('Import a private copy into Knowledge Library. Google Sheets are imported as Excel workbooks.'),
            Expanded(child: rows.isEmpty ? const Center(child: Text('No matching files.')) : ListView(children: rows.map((file) => ListTile(
              leading: Icon(file['folder'] == true ? Icons.folder_outlined : Icons.insert_drive_file_outlined),
              title: Text(file['name'] as String? ?? 'File'),
              trailing: file['folder'] == true ? null : const Icon(Icons.download),
              onTap: file['folder'] == true ? null : () => Navigator.pop(dialogContext, file),
            )).toList())),
          ])),
          actions: [TextButton(onPressed: () => Navigator.pop(dialogContext), child: const Text('Close'))],
        );
      }),
    );
    query.dispose();
    if (selected != null && mounted) {
      await _guard(() async {
        final result = await _api.integrationOperation(name, {'operation': 'import_file', 'remote_id': selected['id'], 'request_key': integrationRequestKey()});
        _notice('Imported ${result['filename']}. Find it in Knowledge Library.');
      });
    }
  }

  Future<void> _mail(String name) async {
    List<Map<String, dynamic>> messages = [];
    await _guard(() async {
      final result = await _api.integrationOperation(name, {'operation': 'mail'});
      messages = (result['messages'] as List).cast<Map<String, dynamic>>();
    });
    if (!mounted || _error != null) return;
    final selected = await showDialog<Map<String, dynamic>>(
      context: context, builder: (context) => AlertDialog(
        title: const Text('Recent mail'),
        content: SizedBox(width: 560, height: 400, child: ListView(children: messages.map((m) => ListTile(
          title: Text(m['subject'] as String? ?? '(No subject)'),
          subtitle: Text(m['from'] as String? ?? '', maxLines: 1),
          onTap: () => Navigator.pop(context, m),
        )).toList())),
        actions: [TextButton(onPressed: () => Navigator.pop(context), child: const Text('Close'))],
      ),
    );
    if (selected != null && mounted) {
      await _guard(() async {
      final data = await _api.integrationOperation(name, {'operation': 'read_mail', 'remote_id': selected['id']});
      if (!mounted) return;
      await showDialog<void>(context: context, builder: (context) => AlertDialog(
        title: Text(data['subject'] as String? ?? 'Message'),
        content: SizedBox(width: 600, child: SingleChildScrollView(child: SelectableText(data['untrusted_body'] as String? ?? ''))),
        actions: [TextButton(onPressed: () => Navigator.pop(context), child: const Text('Close'))],
      ));
      });
    }
  }

  Future<void> _draft(String name) async {
    final to = TextEditingController(), subject = TextEditingController(), body = TextEditingController();
    final values = await showDialog<Map<String, dynamic>>(context: context, builder: (context) => AlertDialog(
      title: const Text('Save an email draft'),
      content: SizedBox(width: 560, child: SingleChildScrollView(child: Column(mainAxisSize: MainAxisSize.min, children: [
        TextField(controller: to, decoration: const InputDecoration(labelText: 'Recipient email'), keyboardType: TextInputType.emailAddress),
        TextField(controller: subject, decoration: const InputDecoration(labelText: 'Subject'), maxLength: 300),
        TextField(controller: body, decoration: const InputDecoration(labelText: 'Message'), minLines: 5, maxLines: 10, maxLength: 20000),
        const Text('Saved in your mailbox for review. Sending is not enabled in Dhanz.'),
      ]))),
      actions: [TextButton(onPressed: () => Navigator.pop(context), child: const Text('Cancel')),
        FilledButton(onPressed: () => Navigator.pop(context, {'operation': 'save_draft', 'to': to.text.trim(),
          'subject': subject.text, 'body': body.text, 'request_key': integrationRequestKey()}), child: const Text('Save draft'))],
    ));
    to.dispose(); subject.dispose(); body.dispose();
    if (values != null && mounted) {
      await _guard(() async {
        await _api.integrationOperation(name, values);
        _notice('Draft saved in your mailbox. No email was sent.');
      });
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(leading: IconButton(onPressed: () => context.go('/settings'), icon: const Icon(Icons.arrow_back)),
      title: const Text('Integrations'), actions: [IconButton(onPressed: _busy ? null : _load, icon: const Icon(Icons.refresh), tooltip: 'Refresh connections')]),
    body: ListView(padding: const EdgeInsets.all(20), children: [
      const Text('Connect your accounts', style: TextStyle(fontSize: 24, fontWeight: FontWeight.bold)),
      const Text('Choose file and mail access separately. Sign in on Microsoft or Google; your provider password stays there.'),
      if (_busy) const LinearProgressIndicator(),
      if (_error != null) Padding(padding: const EdgeInsets.all(12), child: SelectableText(_error!, style: TextStyle(color: Theme.of(context).colorScheme.error))),
      ..._connections.map((item) {
        final name = item['provider'] as String, microsoft = name == 'microsoft';
        final connected = item['connected'] == true, configured = item['configured'] == true;
        final granted = (item['services'] as List? ?? []).cast<String>();
        return Card(child: Padding(padding: const EdgeInsets.all(16), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(microsoft ? 'Microsoft 365' : 'Google', style: const TextStyle(fontSize: 20, fontWeight: FontWeight.bold)),
          Text(microsoft ? 'OneDrive · Excel · Outlook' : 'Drive · Sheets · Gmail'),
          Text(connected ? 'Connected: ${item['account']}' : configured ? 'Not connected' : 'Server setup required. Ask your Dhanz administrator to configure this connection.'),
          CheckboxListTile(contentPadding: EdgeInsets.zero, title: Text(microsoft ? 'OneDrive and Excel files' : 'Drive and Sheets files'),
            subtitle: const Text('Import files, edit with Dhanz, and save new cloud copies.'),
            value: _services[name]!.contains('files'), onChanged: _busy ? null : (v) => setState(() { if (v == true) { _services[name]!.add('files'); } else { _services[name]!.remove('files'); } })),
          CheckboxListTile(contentPadding: EdgeInsets.zero, title: Text(microsoft ? 'Outlook mail' : 'Gmail'),
            subtitle: const Text('Read mail and save drafts for review.'), value: _services[name]!.contains('mail'),
            onChanged: _busy ? null : (v) => setState(() { if (v == true) { _services[name]!.add('mail'); } else { _services[name]!.remove('mail'); } })),
          Wrap(spacing: 8, runSpacing: 8, children: [
            FilledButton(onPressed: _busy || !configured || _services[name]!.isEmpty ? null : () => _connect(name), child: Text(connected ? 'Reconnect' : 'Connect')),
            if (connected) OutlinedButton(onPressed: _busy ? null : () => _disconnect(name), child: const Text('Disconnect')),
            if (connected && granted.contains('files')) OutlinedButton.icon(onPressed: _busy ? null : () => _files(name), icon: const Icon(Icons.folder_open), label: const Text('Browse files')),
            if (connected && granted.contains('mail')) OutlinedButton(onPressed: _busy ? null : () => _mail(name), child: const Text('Read mail')),
            if (connected && granted.contains('mail')) OutlinedButton(onPressed: _busy ? null : () => _draft(name), child: const Text('New draft')),
          ]),
          if (_pending[name] != null) Padding(padding: const EdgeInsets.only(top: 12), child: FilledButton.icon(
            icon: const Icon(Icons.open_in_new), label: Text('Continue to ${microsoft ? 'Microsoft' : 'Google'} sign-in'),
            onPressed: () async {
              try {
                final opened = await launchUrl(_pending[name]!, mode: LaunchMode.externalApplication, webOnlyWindowName: '_blank');
                if (!opened) _notice('Your browser could not open sign-in. Try again from this browser.');
              } catch (_) { _notice('Sign-in could not open. Refresh and reconnect.'); }
            },
          )),
        ])));
      }),
      const SizedBox(height: 12),
      const Text('After connecting, ask in chat to find a cloud file, import a workbook, save an edited copy to Drive/OneDrive, or draft an email. Google Sheets can be imported as Excel and created from an XLSX copy.'),
      ListTile(leading: const Icon(Icons.code), title: const Text('GitHub repositories'), onTap: () => context.go('/github')),
      ListTile(leading: const Icon(Icons.dns_outlined), title: const Text('Connected AWS operations'), onTap: () => context.go('/operations')),
    ]),
  );
}
