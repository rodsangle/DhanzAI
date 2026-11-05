import 'dart:typed_data';

class FolderFile {
  FolderFile(this.path, this.size, this.read);
  final String path;
  final int size;
  final Future<Uint8List> Function() read;
}

bool excludeFolderPath(String name) {
  final parts = name.replaceAll('\\', '/').split('/');
  const excluded = {
    '.git',
    '.svn',
    '.hg',
    'node_modules',
    '.venv',
    'venv',
    '__pycache__',
    '.dart_tool',
    'build',
    '.ssh',
    '.aws',
  };
  return parts.any(
    (p) =>
        excluded.contains(p.toLowerCase()) ||
        p.toLowerCase().startsWith('.env') ||
        const {
          '.pem',
          '.key',
          '.p12',
          '.pfx',
        }.any((suffix) => p.toLowerCase().endsWith(suffix)) ||
        const {'credentials', 'id_rsa', 'id_ed25519'}.contains(p.toLowerCase()),
  );
}

List<FolderFile> checkedFolderFiles(List<FolderFile> files) {
  final allowed = files.where((f) => !excludeFolderPath(f.path)).toList();
  if (allowed.isEmpty) {
    throw const FormatException(
      'No files remain after excluding private and generated folders.',
    );
  }
  if (allowed.length > 200 ||
      allowed.fold<int>(0, (total, f) => total + f.size) > 20 * 1024 * 1024) {
    throw const FormatException(
      'Choose a smaller folder: at most 200 files and 20 MB before compression.',
    );
  }
  final paths = <String>{};
  for (final file in allowed) {
    if (file.path.startsWith('/') ||
        file.path.contains('\\') ||
        file.path.contains(':') ||
        file.path.split('/').any((p) => p == '..' || p.isEmpty) ||
        !paths.add(file.path) ||
        file.path.length > 500) {
      throw const FormatException(
        'Folder contains an unsafe or duplicate relative file path.',
      );
    }
  }
  return allowed;
}
