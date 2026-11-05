import 'dart:async';
import 'dart:js_interop';

import 'package:web/web.dart' as web;

import 'folder_types.dart';

@JS()
extension type _DirectoryFile(web.File file) {
  external String get webkitRelativePath;
}

Future<List<FolderFile>> pickFolder() {
  final done = Completer<List<FolderFile>>();
  final input = web.HTMLInputElement()
    ..type = 'file'
    ..multiple = true;
  input.setAttribute('webkitdirectory', '');
  input.style.display = 'none';
  input.addEventListener(
    'change',
    ((web.Event event) {
      final files = input.files;
      final result = <FolderFile>[];
      if (files != null) {
        for (var i = 0; i < files.length; i++) {
          final file = files.item(i)!;
          final path = _DirectoryFile(file).webkitRelativePath;
          result.add(
            FolderFile(
              path.isEmpty ? file.name : path,
              file.size,
              () async =>
                  (await file.arrayBuffer().toDart).toDart.asUint8List(),
            ),
          );
        }
      }
      input.remove();
      if (!done.isCompleted) done.complete(result);
    }).toJS,
  );
  input.addEventListener(
    'cancel',
    ((web.Event event) {
      input.remove();
      if (!done.isCompleted) done.complete([]);
    }).toJS,
  );
  web.document.body?.append(input);
  input.click();
  return done.future;
}
