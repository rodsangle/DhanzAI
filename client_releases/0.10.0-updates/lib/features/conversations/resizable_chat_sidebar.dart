import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../core/storage/secure_store.dart';

/// Desktop chat split with a device-local saved width and a fixed tool rail.
class ResizableChatSidebar extends StatefulWidget {
  const ResizableChatSidebar({
    super.key,
    required this.store,
    required this.sidebar,
    required this.child,
  });

  final SecureStore store;
  final Widget sidebar;
  final Widget child;
  static const storageKey = 'chat_sidebar_width';

  @override
  State<ResizableChatSidebar> createState() => _ResizableChatSidebarState();
}

class _ResizableChatSidebarState extends State<ResizableChatSidebar> {
  double _width = 364;
  bool _touched = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final saved = double.tryParse(await widget.store.read(ResizableChatSidebar.storageKey) ?? '');
      if (mounted && !_touched && saved != null && saved.isFinite) {
        setState(() => _width = saved.clamp(300.0, 520.0).toDouble());
      }
    } catch (_) {
      // Resizing remains available when device storage is unavailable.
    }
  }

  Future<void> _save() async {
    try {
      await widget.store.write(ResizableChatSidebar.storageKey, _width.toString());
    } catch (_) {
      // Keep the width for this session if device storage is unavailable.
    }
  }

  void _resize(double width, double maximum, {bool save = false}) {
    _touched = true;
    setState(() => _width = width.clamp(300.0, maximum).toDouble());
    if (save) _save();
  }

  @override
  Widget build(BuildContext context) => LayoutBuilder(
    builder: (context, constraints) {
      final maximum = math.max(300.0, math.min(520.0, constraints.maxWidth - 492));
      final width = _width.clamp(300.0, maximum).toDouble();
      return Row(
        children: [
          SizedBox(key: const ValueKey('chat-history-width'), width: width, child: widget.sidebar),
          Semantics(
            label: 'Resize chat history',
            value: '${width.round()} pixels',
            increasedValue: '${(width + 24).clamp(300.0, maximum).round()} pixels',
            decreasedValue: '${(width - 24).clamp(300.0, maximum).round()} pixels',
            onIncrease: () => _resize(width + 24, maximum, save: true),
            onDecrease: () => _resize(width - 24, maximum, save: true),
            child: Focus(
              onKeyEvent: (node, event) {
                if (event is KeyDownEvent || event is KeyRepeatEvent) {
                  if (event.logicalKey == LogicalKeyboardKey.arrowRight) {
                    _resize(width + 24, maximum, save: true);
                    return KeyEventResult.handled;
                  }
                  if (event.logicalKey == LogicalKeyboardKey.arrowLeft) {
                    _resize(width - 24, maximum, save: true);
                    return KeyEventResult.handled;
                  }
                  if (event.logicalKey == LogicalKeyboardKey.home) {
                    _resize(364, maximum, save: true);
                    return KeyEventResult.handled;
                  }
                }
                return KeyEventResult.ignored;
              },
              child: Tooltip(
                message: 'Drag to resize chat history. Double-click to reset. Keyboard: left/right arrows.',
                child: MouseRegion(
                  cursor: SystemMouseCursors.resizeColumn,
                  child: GestureDetector(
                    key: const ValueKey('chat-history-resizer'),
                    behavior: HitTestBehavior.opaque,
                    onHorizontalDragUpdate: (details) => _resize(_width.clamp(300.0, maximum).toDouble() + details.delta.dx, maximum),
                    onHorizontalDragEnd: (_) => _save(),
                    onHorizontalDragCancel: _save,
                    onDoubleTap: () => _resize(364, maximum, save: true),
                    child: SizedBox(
                      width: 12,
                      child: Center(child: Container(
                        width: 3,
                        height: 36,
                        decoration: BoxDecoration(
                          color: Theme.of(context).colorScheme.outlineVariant,
                          borderRadius: BorderRadius.circular(4),
                        ),
                      )),
                    ),
                  ),
                ),
              ),
            ),
          ),
          Expanded(child: widget.child),
        ],
      );
    },
  );
}
