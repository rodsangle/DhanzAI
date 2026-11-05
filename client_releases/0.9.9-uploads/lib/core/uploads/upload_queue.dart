import 'dart:async';
import 'dart:typed_data';

import 'package:archive/archive.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../features/auth/auth_controller.dart';
import '../../features/library/library_controller.dart';
import '../../models/models.dart';
import '../api/api_client.dart';
import '../files.dart';
import '../folder_types.dart';
import '../providers.dart';

enum UploadStatus { queued, preparing, uploading, completed, failed, cancelled }

class UploadTicket {
  const UploadTicket(this.userId, this.server, this.epoch);
  final String userId;
  final String server;
  final int epoch;
}

class UploadEntry {
  const UploadEntry({
    required this.id,
    required this.name,
    required this.status,
    required this.size,
    this.projectId,
    this.target,
    this.attachable = false,
    this.document,
    this.error,
  });
  final int id;
  final String name;
  final int size;
  final UploadStatus status;
  final String? projectId;
  final String? target;
  final bool attachable;
  final KnowledgeDocument? document;
  final String? error;
  bool get busy => const [
    UploadStatus.queued,
    UploadStatus.preparing,
    UploadStatus.uploading,
  ].contains(status);
  String get label => switch (status) {
    UploadStatus.queued => 'Queued',
    UploadStatus.preparing => 'Preparing files',
    UploadStatus.uploading => 'Uploading and processing on server',
    UploadStatus.completed => 'Saved to library',
    UploadStatus.failed => 'Upload needs attention',
    UploadStatus.cancelled => 'Cancelled before upload',
  };
}

class _Upload {
  _Upload(
    this.id,
    this.name,
    this.size,
    this.projectId,
    this.target,
    this.prepare,
  );
  final int id;
  final String name;
  final int size;
  final String? projectId;
  String? target;
  Future<Uint8List> Function()? prepare;
  UploadStatus status = UploadStatus.queued;
  KnowledgeDocument? document;
  String? error;
  bool attachable = true;
  final done = Completer<void>();
  UploadEntry get snapshot => UploadEntry(
    id: id,
    name: name,
    status: status,
    size: size,
    projectId: projectId,
    target: target,
    attachable: attachable && target != null,
    document: document,
    error: error,
  );
}

/// This non-auto-dispose provider belongs to the app, never a route or a chat.
class UploadQueue extends Notifier<List<UploadEntry>> {
  final _jobs = <_Upload>[];
  int _epoch = 0;
  int _nextId = 0;
  int? _runningEpoch;
  String? _owner;
  String _server = '';

  @override
  List<UploadEntry> build() {
    _owner = ref.watch(authControllerProvider.select((s) => s.value?.id));
    ref.watch(connectionRevisionProvider);
    _server = ref.watch(apiClientProvider).baseUrl;
    _epoch++;
    for (final job in _jobs) {
      if (!job.done.isCompleted) job.done.complete();
    }
    _jobs.clear();
    ref.onDispose(() => _epoch++);
    return const [];
  }

  UploadTicket ticket() {
    if (_owner == null) throw StateError('Sign in before uploading.');
    return UploadTicket(_owner!, _server, _epoch);
  }

  bool accepts(UploadTicket ticket) =>
      ref.mounted &&
      ticket.epoch == _epoch &&
      ticket.userId == _owner &&
      ticket.userId == ref.read(authControllerProvider).value?.id &&
      ticket.server == ref.read(apiClientProvider).baseUrl;

  void _publish() => state = [for (final job in _jobs) job.snapshot];

  void _checkRoom(int count, int bytes) {
    final retainedBytes = _jobs
        .where((j) => j.prepare != null)
        .fold<int>(0, (n, j) => n + j.size);
    if (_jobs.where((j) => j.snapshot.busy).length + count > 200 ||
        retainedBytes + bytes > 100 * 1024 * 1024) {
      throw StateError(
        'Upload queue is full. Wait for uploads or clear finished items before adding more.',
      );
    }
  }

  List<int> files(
    List<PickedFile> files, {
    required UploadTicket ticket,
    String? projectId,
    String? target,
  }) {
    if (!accepts(ticket)) return [];
    _checkRoom(files.length, files.fold<int>(0, (n, f) => n + f.bytes.length));
    final ids = <int>[];
    for (final file in files) {
      final job = _Upload(
        ++_nextId,
        file.name,
        file.bytes.length,
        projectId,
        target,
        () async => file.bytes,
      );
      _jobs.add(job);
      ids.add(job.id);
    }
    _publish();
    unawaited(_drain(ticket));
    return ids;
  }

  int? folder(
    List<FolderFile> selected, {
    required UploadTicket ticket,
    String? projectId,
    String? target,
  }) {
    if (!accepts(ticket)) return null;
    final files = checkedFolderFiles(selected);
    final size = files.fold<int>(0, (n, f) => n + f.size);
    _checkRoom(1, size);
    final base = files.first.path
        .split('/')
        .first
        .replaceAll(RegExp(r'[^A-Za-z0-9_-]'), '_');
    final name =
        '${base.length > 80 ? base.substring(0, 80) : base}.dhanz-folder.zip';
    final job = _Upload(++_nextId, name, size, projectId, target, null);
    job.prepare = () async {
      final archive = Archive();
      for (final file in files) {
        if (!accepts(ticket) || job.status == UploadStatus.cancelled)
          throw StateError('Upload cancelled.');
        final bytes = await file.read();
        if (bytes.length != file.size)
          throw const FormatException(
            'A file changed; select the folder again.',
          );
        archive.addFile(ArchiveFile(file.path, bytes.length, bytes));
      }
      return Uint8List.fromList(ZipEncoder().encode(archive));
    };
    _jobs.add(job);
    _publish();
    unawaited(_drain(ticket));
    return job.id;
  }

  Future<void> waitFor(int id) async {
    final job = _jobs.where((j) => j.id == id).firstOrNull;
    if (job != null) await job.done.future;
  }

  Future<void> _drain(UploadTicket ticket) async {
    if (_runningEpoch == ticket.epoch || !accepts(ticket)) return;
    _runningEpoch = ticket.epoch;
    try {
      while (accepts(ticket)) {
        final job = _jobs
            .where((j) => j.status == UploadStatus.queued)
            .firstOrNull;
        if (job == null) break;
        job.status = UploadStatus.preparing;
        _publish();
        try {
          final bytes = await job.prepare!();
          if (!accepts(ticket)) return;
          if (job.status == UploadStatus.cancelled) continue;
          job.status = UploadStatus.uploading;
          _publish();
          final document = await ref
              .read(apiClientProvider)
              .uploadFile(
                job.name,
                bytes,
                projectId: job.projectId,
                isCurrentSession: () => accepts(ticket),
              );
          if (!accepts(ticket)) return;
          job.document = document;
          job.status = UploadStatus.completed;
          job.prepare =
              null; // release the selected bytes/browser handles after success
          ref.invalidate(libraryProvider);
        } catch (error) {
          if (!accepts(ticket)) return;
          if (job.status != UploadStatus.cancelled) {
            job.status = UploadStatus.failed;
            job.error = error is ApiException ? error.message : '$error';
          }
        } finally {
          if (!job.done.isCompleted) job.done.complete();
          if (accepts(ticket)) _publish();
        }
      }
    } finally {
      if (_runningEpoch == ticket.epoch) _runningEpoch = null;
    }
  }

  void cancel(int id) {
    final job = _jobs.where((j) => j.id == id).firstOrNull;
    if (job == null ||
        !const [
          UploadStatus.queued,
          UploadStatus.preparing,
        ].contains(job.status))
      return;
    job.status = UploadStatus.cancelled;
    job.prepare = null;
    if (!job.done.isCompleted) job.done.complete();
    _publish();
  }

  void retry(int id) {
    final old = _jobs.where((j) => j.id == id).firstOrNull;
    if (old == null || old.status != UploadStatus.failed || old.prepare == null)
      return;
    final next = _Upload(
      ++_nextId,
      old.name,
      old.size,
      old.projectId,
      old.target,
      old.prepare,
    );
    old.prepare = null;
    old.attachable = false;
    _jobs.add(next);
    _publish();
    unawaited(
      _drain(ticket()),
    ); // only an explicit retry; failed POSTs are never replayed automatically
  }

  void consume(String target, Iterable<String> documentIds) {
    for (final job in _jobs) {
      if (job.target == target && documentIds.contains(job.document?.id))
        job.attachable = false;
    }
    _publish();
  }

  void retarget(String from, String to) {
    for (final job in _jobs) {
      if (job.target == from) job.target = to;
    }
    _publish();
  }

  void clearFinished() {
    _jobs.removeWhere(
      (j) => !j.snapshot.busy && !(j.snapshot.attachable && j.document != null),
    );
    _publish();
  }
}

final uploadQueueProvider = NotifierProvider<UploadQueue, List<UploadEntry>>(
  UploadQueue.new,
);
