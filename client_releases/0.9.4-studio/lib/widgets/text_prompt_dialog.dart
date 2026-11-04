import 'package:flutter/material.dart';

/// Shows a dialog with one text field. Returns the entered text, or null if cancelled.
///
/// The dialog owns its TextEditingController, so it stays valid during the closing animation.
Future<String?> showTextPrompt(
  BuildContext context, {
  required String title,
  required String confirmLabel,
  String initialText = '',
  String? label,
  String? hint,
  Widget? message,
  Widget? help,
  int minLines = 1,
  int maxLines = 1,
  int? maxLength,
  bool obscureText = false,
  bool destructive = false,
  TextInputType? keyboardType,
  IconData? prefixIcon,
}) {
  return showDialog<String>(
    context: context,
    builder: (context) => _TextPromptDialog(
      title: title,
      confirmLabel: confirmLabel,
      initialText: initialText,
      label: label,
      hint: hint,
      message: message,
      help: help,
      minLines: minLines,
      maxLines: maxLines,
      maxLength: maxLength,
      obscureText: obscureText,
      destructive: destructive,
      keyboardType: keyboardType,
      prefixIcon: prefixIcon,
    ),
  );
}

class _TextPromptDialog extends StatefulWidget {
  const _TextPromptDialog({
    required this.title,
    required this.confirmLabel,
    required this.initialText,
    required this.minLines,
    required this.maxLines,
    required this.obscureText,
    required this.destructive,
    this.label,
    this.hint,
    this.message,
    this.help,
    this.maxLength,
    this.keyboardType,
    this.prefixIcon,
  });

  final String title;
  final String confirmLabel;
  final String initialText;
  final String? label;
  final String? hint;
  final Widget? message;
  final Widget? help;
  final int minLines;
  final int maxLines;
  final int? maxLength;
  final bool obscureText;
  final bool destructive;
  final TextInputType? keyboardType;
  final IconData? prefixIcon;

  @override
  State<_TextPromptDialog> createState() => _TextPromptDialogState();
}

class _TextPromptDialogState extends State<_TextPromptDialog> {
  late final TextEditingController _controller = TextEditingController(text: widget.initialText);

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  void _submit() => Navigator.pop(context, _controller.text);

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: Text(widget.title),
      content: SizedBox(
        width: 520,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (widget.message != null) ...[widget.message!, const SizedBox(height: 16)],
            TextField(
              controller: _controller,
              autofocus: true,
              minLines: widget.minLines,
              maxLines: widget.maxLines,
              maxLength: widget.maxLength,
              obscureText: widget.obscureText,
              keyboardType: widget.keyboardType,
              decoration: InputDecoration(
                labelText: widget.label,
                hintText: widget.hint,
                prefixIcon: widget.prefixIcon == null ? null : Icon(widget.prefixIcon),
              ),
              onSubmitted: widget.maxLines == 1 ? (_) => _submit() : null,
            ),
            if (widget.help != null) ...[const SizedBox(height: 12), widget.help!],
          ],
        ),
      ),
      actions: [
        TextButton(onPressed: () => Navigator.pop(context), child: const Text('Cancel')),
        FilledButton(
          style: widget.destructive
              ? FilledButton.styleFrom(backgroundColor: Theme.of(context).colorScheme.error)
              : null,
          onPressed: _submit,
          child: Text(widget.confirmLabel),
        ),
      ],
    );
  }
}
