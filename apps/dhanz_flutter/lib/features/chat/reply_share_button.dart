import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:share_plus/share_plus.dart';

typedef ReplySharer = Future<ShareResult> Function(ShareParams params);

/// Shares only this reply's text. Never creates a public link or exports chat history.
class ReplyShareButton extends StatefulWidget {
  const ReplyShareButton({super.key, required this.text, this.share});
  final String text;
  final ReplySharer? share;

  @override
  State<ReplyShareButton> createState() => _ReplyShareButtonState();
}

class _ReplyShareButtonState extends State<ReplyShareButton> {
  bool _busy = false;

  Future<void> _share() async {
    if (_busy || widget.text.isEmpty) return;
    // Capture the selected reply before the asynchronous platform UI opens.
    final text = widget.text;
    final box = context.findRenderObject() as RenderBox?;
    final origin = box != null && box.hasSize ? box.localToGlobal(Offset.zero) & box.size : null;
    setState(() => _busy = true);
    try {
      await (widget.share ?? SharePlus.instance.share)(
        ShareParams(
          text: text,
          title: 'Dhanz AI reply',
          subject: 'Dhanz AI reply',
          sharePositionOrigin: origin,
          downloadFallbackEnabled: false,
          mailToFallbackEnabled: false,
        ),
      );
      // A dismissed share sheet is not a request to copy. Some browsers also
      // return "unavailable" after a successful handoff: don't claim delivery.
    } catch (_) {
      if (mounted) await _copyFallback(text);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _copyFallback(String text) async {
    String? error;
    bool copying = false;
    await showDialog<void>(
      context: context,
      builder: (dialogContext) => StatefulBuilder(
        builder: (context, setDialogState) => AlertDialog(
          title: const Text('Share reply'),
          content: SizedBox(
            width: 560,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  'The device share menu is unavailable here. Copy this reply and paste it into the app you want.',
                ),
                const SizedBox(height: 12),
                SizedBox(
                  height: MediaQuery.sizeOf(context).height * 0.35,
                  child: SingleChildScrollView(child: SelectableText(text)),
                ),
                if (error != null) Text(error!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
              ],
            ),
          ),
          actions: [
            TextButton(onPressed: copying ? null : () => Navigator.pop(dialogContext), child: const Text('Cancel')),
            FilledButton.icon(
              icon: const Icon(Icons.copy_rounded),
              label: const Text('Copy reply'),
              onPressed: copying
                  ? null
                  : () async {
                      setDialogState(() => copying = true);
                      try {
                        await Clipboard.setData(ClipboardData(text: text));
                        if (dialogContext.mounted) Navigator.pop(dialogContext);
                        if (mounted) {
                          ScaffoldMessenger.of(this.context)
                              .showSnackBar(const SnackBar(content: Text('Reply copied')));
                        }
                      } catch (_) {
                        if (dialogContext.mounted) {
                          setDialogState(() {
                            copying = false;
                            error = 'Clipboard access is unavailable. Select the text above and copy it manually.';
                          });
                        }
                      }
                    },
            ),
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) => IconButton(
    tooltip: 'Share reply',
    icon: const Icon(Icons.share_outlined),
    iconSize: 18,
    visualDensity: VisualDensity.compact,
    onPressed: _busy || widget.text.isEmpty ? null : _share,
  );
}
