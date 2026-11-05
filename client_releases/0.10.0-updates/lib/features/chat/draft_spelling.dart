import 'package:flutter/material.dart';

// An intentionally small offline helper, not a general grammar checker.
const _commonTypos = <String, String>{
  'teh': 'the',
  'adn': 'and',
  'hte': 'the',
  'wiht': 'with',
  'recieve': 'receive',
  'recieved': 'received',
  'reciept': 'receipt',
  'seperate': 'separate',
  'seperately': 'separately',
  'definately': 'definitely',
  'thier': 'their',
  'becuase': 'because',
  'adress': 'address',
  'occured': 'occurred',
  'untill': 'until',
  'tommorow': 'tomorrow',
  'tommorrow': 'tomorrow',
  'enviroment': 'environment',
  'realy': 'really',
  'completly': 'completely',
  'wierd': 'weird',
  'beleive': 'believe',
  'succesful': 'successful',
  'sucess': 'success',
  'downlaod': 'download',
  'speling': 'spelling',
  'writting': 'writing',
  'grammer': 'grammar',
  'messege': 'message',
  'tahnks': 'thanks',
  'plaese': 'please',
};

/// Suggest common English typo fixes, protecting fenced code and technical tokens.
/// Nothing leaves this device. Applying the result always requires a preview.
String suggestDraftSpelling(String text) {
  final trimmed = text.trimLeft();
  if (trimmed.startsWith('{') || trimmed.startsWith('[') || trimmed.startsWith('<') || trimmed.startsWith('#!')) {
    return text;
  }
  final technicalLine = RegExp(
    r'^[ \t]*(?:sudo |docker |git |curl |python3? |npm |node |pip |Get-|Set-|'
    r'[A-Za-z_][A-Za-z0-9_.]*[ \t]*(?:=|\())',
    multiLine: true,
  );
  final prose = text.replaceAll(RegExp(r'```[\s\S]*?(?:```|$)'), '');
  if (technicalLine.hasMatch(prose)) return text;
  // Protected tokens take precedence over whole-word matches. An unclosed code
  // fence is protected to the end, and inline code is protected to the line end.
  final tokens = RegExp(
    r'```[\s\S]*?(?:```|$)|`[^\r\n]*|https?://[^\s]+|'
    r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}|'
    r'(?:[A-Za-z]:\\|\.{0,2}/)[^\s]+|'
    r'\b[A-Za-z0-9][A-Za-z0-9.-]*\.[A-Za-z]{2,}(?:/[^\s]*)?|'
    r'\b[A-Za-z0-9_.-]+[/\\][^\s]+|'
    r'\b[A-Za-z0-9_]+(?:[-_][A-Za-z0-9_]+)+\b|'
    r'\b[A-Za-z]+\b',
  );
  return text.replaceAllMapped(tokens, (match) {
    final word = match[0]!;
    final corrected = _commonTypos[word.toLowerCase()];
    if (corrected == null) return word;
    if (word == word.toUpperCase()) return corrected.toUpperCase();
    if (word[0] == word[0].toUpperCase()) {
      return corrected[0].toUpperCase() + corrected.substring(1);
    }
    return corrected;
  });
}

class DraftSpellingButton extends StatefulWidget {
  const DraftSpellingButton({
    super.key,
    required this.controller,
    required this.deviceAutocorrect,
    required this.onDeviceAutocorrectChanged,
    this.enabled = true,
  });

  final TextEditingController controller;
  final bool deviceAutocorrect;
  final ValueChanged<bool> onDeviceAutocorrectChanged;
  final bool enabled;

  @override
  State<DraftSpellingButton> createState() => _DraftSpellingButtonState();
}

class _DraftSpellingButtonState extends State<DraftSpellingButton> {
  bool _reviewing = false;

  void _notice(String text) {
    if (mounted) ScaffoldMessenger.maybeOf(context)?.showSnackBar(SnackBar(content: Text(text)));
  }

  Future<void> _review() async {
    if (_reviewing || !widget.enabled) return;
    final original = widget.controller.text;
    final suggested = suggestDraftSpelling(original);
    if (suggested == original) {
      _notice('No common English typo fixes found. Your device may offer other spelling suggestions.');
      return;
    }
    setState(() => _reviewing = true);
    try {
      final apply = await showDialog<bool>(
        context: context,
        builder: (context) => AlertDialog(
          title: const Text('Review spelling'),
          content: SizedBox(
            width: 560,
            child: SingleChildScrollView(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text('Common English typo fixes. Nothing is sent to AI.'),
                  const SizedBox(height: 16),
                  const Text('Original'),
                  const SizedBox(height: 6),
                  SelectableText(original),
                  const SizedBox(height: 16),
                  const Text('Suggested draft'),
                  const SizedBox(height: 6),
                  SelectableText(suggested),
                ],
              ),
            ),
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
            FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Apply spelling fixes')),
          ],
        ),
      );
      if (!mounted || apply != true) return;
      if (!widget.enabled) {
        _notice('Your draft is queued. Cancel the pending send before editing it.');
        return;
      }
      if (widget.controller.text != original) {
        _notice('Your draft changed. Review spelling again to avoid replacing your edits.');
        return;
      }
      widget.controller.value = TextEditingValue(
        text: suggested,
        selection: TextSelection.collapsed(offset: suggested.length),
      );
      ScaffoldMessenger.maybeOf(context)?.showSnackBar(
        SnackBar(
          content: const Text('Spelling fixes applied'),
          action: SnackBarAction(
            label: 'Undo',
            onPressed: () {
              if (!mounted) return;
              if (widget.controller.text != suggested) {
                _notice('Your draft changed; undo was not applied.');
                return;
              }
              widget.controller.value = TextEditingValue(
                text: original,
                selection: TextSelection.collapsed(offset: original.length),
              );
            },
          ),
        ),
      );
    } finally {
      if (mounted) setState(() => _reviewing = false);
    }
  }

  @override
  Widget build(BuildContext context) => ListenableBuilder(
    listenable: widget.controller,
    builder: (context, _) => PopupMenuButton<String>(
      tooltip: 'Spelling options',
      enabled: widget.enabled && !_reviewing,
      icon: const Icon(Icons.spellcheck),
      onSelected: (value) async {
        if (value == 'toggle') {
          widget.onDeviceAutocorrectChanged(!widget.deviceAutocorrect);
        } else if (value == 'review') {
          await _review();
        }
      },
      itemBuilder: (context) => [
        CheckedPopupMenuItem(
          value: 'toggle',
          checked: widget.deviceAutocorrect,
          child: const Text('Device autocorrect'),
        ),
        PopupMenuItem(
          value: 'review',
          enabled: widget.controller.text.trim().isNotEmpty,
          child: const Text('Review spelling fixes'),
        ),
      ],
    ),
  );
}
