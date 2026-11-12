import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

class ChatPreviewTarget {
  const ChatPreviewTarget({required this.documentId, required this.filename, this.simulator = false, this.projectId});
  final String documentId;
  final String filename;
  final bool simulator;
  final String? projectId;
}

class ChatPreviewController extends ChangeNotifier {
  final chatKey = GlobalKey();
  final previewKey = GlobalKey();
  ChatPreviewTarget? target;
  bool visible = false;
  bool expanded = false;
  double width = 420;
  Future<bool> Function()? beforeClose;
  bool _confirming = false;

  Future<bool> _canLeave() async {
    if (_confirming) return false;
    _confirming = true;
    try {
      return beforeClose == null || await beforeClose!();
    } finally {
      _confirming = false;
    }
  }

  Future<void> open(ChatPreviewTarget file) async {
    if (target?.documentId != file.documentId && !await _canLeave()) return;
    target = file;
    visible = true;
    notifyListeners();
  }

  void replaceTarget(ChatPreviewTarget file) {
    target = file;
    notifyListeners();
  }

  void show() {
    visible = true;
    notifyListeners();
  }

  Future<void> close() async {
    if (!await _canLeave()) return;
    visible = false;
    notifyListeners();
  }

  void toggleExpanded() {
    expanded = !expanded;
    notifyListeners();
  }

  void resize(double delta, double maximum) {
    width = (width - delta).clamp(300.0, maximum).toDouble();
    notifyListeners();
  }

  void clear({bool notify = true}) {
    beforeClose = null;
    target = null;
    visible = false;
    expanded = false;
    if (notify) notifyListeners();
  }
}

class ChatPreviewScope extends InheritedNotifier<ChatPreviewController> {
  const ChatPreviewScope({
    super.key,
    required ChatPreviewController controller,
    required super.child,
  }) : super(notifier: controller);

  static ChatPreviewController? of(BuildContext context) =>
      context.dependOnInheritedWidgetOfExactType<ChatPreviewScope>()?.notifier;
}

typedef ChatPreviewBuilder = Widget Function(
  BuildContext context,
  ChatPreviewTarget target,
);

class ChatPreviewHost extends StatelessWidget {
  const ChatPreviewHost({
    super.key,
    required this.controller,
    required this.child,
    required this.previewBuilder,
  });
  final ChatPreviewController controller;
  final Widget child;
  final ChatPreviewBuilder previewBuilder;

  @override
  Widget build(BuildContext context) => ChatPreviewScope(
    controller: controller,
    child: AnimatedBuilder(
      animation: controller,
      child: child,
      builder: (context, child) => LayoutBuilder(
        builder: (context, constraints) {
          final chatBody = KeyedSubtree(key: controller.chatKey, child: child!);
          if (!controller.visible) return chatBody;
          final split = constraints.maxWidth >= 900 && !controller.expanded;
          final maximum = split
              ? constraints.maxWidth - 352
              : constraints.maxWidth;
          final width = split
              ? controller.width.clamp(300.0, maximum).toDouble()
              : constraints.maxWidth;
          final target = controller.target;
          final panel = Material(
            key: const ValueKey('chat-preview-panel'),
            elevation: split ? 1 : 12,
            color: Theme.of(context).colorScheme.surface,
            child: Column(
              children: [
                Padding(
                  padding: const EdgeInsets.fromLTRB(16, 4, 4, 4),
                  child: Row(
                    children: [
                      Expanded(
                        child: Text(
                          target?.filename ?? 'Preview',
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: Theme.of(context).textTheme.titleMedium,
                        ),
                      ),
                      IconButton(
                        tooltip: controller.expanded
                            ? 'Restore preview size'
                            : 'Expand preview',
                        icon: Icon(
                          controller.expanded
                              ? Icons.fullscreen_exit
                              : Icons.fullscreen,
                        ),
                        onPressed: controller.toggleExpanded,
                      ),
                      IconButton(
                        tooltip: 'Close preview',
                        icon: const Icon(Icons.close),
                        onPressed: controller.close,
                      ),
                    ],
                  ),
                ),
                const Divider(height: 1),
                Expanded(
                  child: target == null
                      ? const Center(
                          child: Padding(
                            padding: EdgeInsets.all(24),
                            child: Text(
                              'Press Preview beside a file in this chat to view it here.',
                            ),
                          ),
                        )
                      : KeyedSubtree(
                          key: controller.previewKey,
                          child: KeyedSubtree(
                            key: ValueKey(target.documentId),
                            child: previewBuilder(context, target),
                          ),
                        ),
                ),
              ],
            ),
          );
          final content = split
              ? Row(
                  children: [
                    Expanded(child: chatBody),
                    Semantics(
                      label: 'Resize preview. Drag left to widen or right to narrow.',
                      onIncrease: () => controller.resize(-40, maximum),
                      onDecrease: () => controller.resize(40, maximum),
                      child: MouseRegion(
                        cursor: SystemMouseCursors.resizeColumn,
                        child: GestureDetector(
                          behavior: HitTestBehavior.opaque,
                          onHorizontalDragUpdate: (details) =>
                              controller.resize(details.delta.dx, maximum),
                          child: SizedBox(
                            key: const ValueKey('preview-resize-handle'),
                            width: 12,
                            child: Center(
                              child: Container(
                                width: 3,
                                color: Theme.of(context).dividerColor,
                              ),
                            ),
                          ),
                        ),
                      ),
                    ),
                    SizedBox(
                      key: const ValueKey('preview-width'),
                      width: width,
                      child: panel,
                    ),
                  ],
                )
              : Stack(
                  children: [
                    chatBody,
                    Positioned.fill(
                      child: ModalBarrier(
                        dismissible: true,
                        color: Colors.black26,
                        onDismiss: controller.close,
                      ),
                    ),
                    Positioned(
                      top: 0,
                      bottom: 0,
                      right: 0,
                      width: width,
                      child: panel,
                    ),
                  ],
                );
          return CallbackShortcuts(
            bindings: {
              const SingleActivator(LogicalKeyboardKey.escape):
                  controller.close,
            },
            child: Focus(autofocus: true, child: content),
          );
        },
      ),
    ),
  );
}
