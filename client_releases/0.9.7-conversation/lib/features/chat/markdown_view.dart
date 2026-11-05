import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_highlight/flutter_highlight.dart';
import 'package:flutter_highlight/themes/atom-one-dark.dart';
import 'package:flutter_highlight/themes/atom-one-light.dart';
import 'package:flutter_markdown_plus/flutter_markdown_plus.dart';
import 'package:highlight/languages/all.dart' show allLanguages;
import 'package:markdown/markdown.dart' as md;
import 'package:url_launcher/url_launcher.dart';

/// Renders assistant Markdown with syntax-highlighted, copyable code blocks.
class MarkdownView extends StatelessWidget {
  const MarkdownView(this.data, {super.key});

  final String data;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final base = MarkdownStyleSheet.fromTheme(theme);
    return MarkdownBody(
      data: data,
      selectable: true,
      extensionSet: md.ExtensionSet.gitHubWeb,
      builders: {'pre': _CodeBlockBuilder()},
      onTapLink: (text, href, title) async {
        final uri = href == null ? null : Uri.tryParse(href);
        if (uri != null && (uri.scheme == 'https' || uri.scheme == 'http')) {
          await launchUrl(uri, mode: LaunchMode.externalApplication);
        }
      },
      styleSheet: base.copyWith(
        // Code blocks draw their own container (see CodeBlock).
        codeblockDecoration: const BoxDecoration(),
        codeblockPadding: EdgeInsets.zero,
        p: theme.textTheme.bodyLarge?.copyWith(height: 1.5),
        code: theme.textTheme.bodyMedium?.copyWith(
          fontFamily: 'monospace',
          backgroundColor: theme.colorScheme.surfaceContainerHighest,
        ),
        blockquoteDecoration: BoxDecoration(
          border: Border(left: BorderSide(color: theme.colorScheme.secondary, width: 3)),
        ),
        a: TextStyle(color: theme.colorScheme.secondary, decoration: TextDecoration.underline),
        tableBorder: TableBorder.all(color: theme.colorScheme.outlineVariant),
      ),
    );
  }
}

class _CodeBlockBuilder extends MarkdownElementBuilder {
  @override
  bool isBlockElement() => true;

  @override
  Widget? visitElementAfterWithContext(
    BuildContext context,
    md.Element element,
    TextStyle? preferredStyle,
    TextStyle? parentStyle,
  ) {
    final codeEl = element.children?.whereType<md.Element>().firstOrNull;
    final cls = codeEl?.attributes['class'] ?? '';
    final language = cls.startsWith('language-') ? cls.substring('language-'.length) : null;
    var code = element.textContent;
    if (code.endsWith('\n')) code = code.substring(0, code.length - 1);
    return CodeBlock(code: code, language: language);
  }
}

class CodeBlock extends StatelessWidget {
  const CodeBlock({super.key, required this.code, this.language});

  final String code;
  final String? language;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final dark = theme.brightness == Brightness.dark;
    final hlTheme = dark ? atomOneDarkTheme : atomOneLightTheme;
    return Container(
      margin: const EdgeInsets.symmetric(vertical: 8),
      decoration: BoxDecoration(
        color: hlTheme['root']?.backgroundColor,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: theme.colorScheme.outlineVariant),
      ),
      clipBehavior: Clip.antiAlias,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Container(
            color: theme.colorScheme.surfaceContainerHigh,
            padding: const EdgeInsets.only(left: 12),
            child: Row(
              children: [
                Text(language ?? 'code', style: theme.textTheme.labelMedium),
                const Spacer(),
                IconButton(
                  tooltip: 'Copy code',
                  visualDensity: VisualDensity.compact,
                  iconSize: 18,
                  icon: const Icon(Icons.copy_rounded),
                  onPressed: () async {
                    await Clipboard.setData(ClipboardData(text: code));
                    if (context.mounted) {
                      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Code copied')));
                    }
                  },
                ),
              ],
            ),
          ),
          SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            child: HighlightView(
              code,
              language: _supported(language),
              theme: hlTheme,
              padding: const EdgeInsets.all(12),
              textStyle: const TextStyle(fontFamily: 'monospace', fontSize: 13.5, height: 1.45),
            ),
          ),
        ],
      ),
    );
  }

  static String _supported(String? lang) {
    const aliases = {
      'py': 'python',
      'js': 'javascript',
      'ts': 'typescript',
      'sh': 'bash',
      'shell': 'bash',
      'yml': 'yaml',
    };
    final l = (lang ?? '').toLowerCase();
    final name = aliases[l] ?? l;
    return allLanguages.containsKey(name) ? name : 'plaintext';
  }
}
