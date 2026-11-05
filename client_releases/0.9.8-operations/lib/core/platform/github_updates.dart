import 'dart:convert';

import 'package:http/http.dart' as http;

import '../../models/models.dart';

/// Only published stable releases in the application's source repository are trusted.
Future<UpdateInfo> checkGitHubRelease(http.Client client, String platform, String current) async {
  final response = await client
      .get(
        Uri.https('api.github.com', '/repos/rodsangle/DhanzAI/releases/latest'),
        headers: {'Accept': 'application/vnd.github+json'},
      )
      .timeout(const Duration(seconds: 20));
  if (response.statusCode != 200) throw StateError('GitHub update check failed (${response.statusCode})');
  final release = jsonDecode(response.body) as Map<String, dynamic>;
  final tag = release['tag_name'] as String;
  final match = RegExp(r'^v?(\d+)\.(\d+)\.(\d+)$').firstMatch(tag);
  if (release['draft'] != false || release['prerelease'] != false || match == null) {
    throw const FormatException('Invalid stable release');
  }
  final latest = tag.replaceFirst(RegExp('^v'), '');
  final old = current.split('+').first.split('.').map(int.parse).toList();
  final next = latest.split('.').map(int.parse).toList();
  var newer = false;
  for (var i = 0; i < 3; i++) {
    final previous = i < old.length ? old[i] : 0;
    if (next[i] != previous) {
      newer = next[i] > previous;
      break;
    }
  }
  final suffix = platform == 'windows'
      ? '-windows-setup.exe'
      : platform == 'android'
      ? '.apk'
      : null;
  if (suffix == null || !newer) {
    return UpdateInfo(currentVersion: current, latestVersion: latest, updateAvailable: false);
  }
  for (final asset in release['assets'] as List) {
    final name = asset['name'] as String;
    final digest = asset['digest'] as String? ?? '';
    final url = Uri.parse(asset['browser_download_url'] as String);
    if (!name.startsWith('dhanz-ai-') ||
        !name.endsWith(suffix) ||
        !RegExp(r'^sha256:[a-fA-F0-9]{64}$').hasMatch(digest) ||
        url.scheme != 'https' ||
        url.host != 'github.com' ||
        !url.path.startsWith('/rodsangle/DhanzAI/releases/download/$tag/')) {
      continue;
    }
    return UpdateInfo(
      currentVersion: current,
      latestVersion: latest,
      updateAvailable: true,
      url: url.toString(),
      sha256: digest.substring(7),
      notes: 'Official GitHub release $latest',
    );
  }
  throw StateError('No verified $platform installer is published for $latest');
}
