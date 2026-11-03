import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/providers.dart';
import '../../core/theme.dart';

/// Settings → Appearance → Theme: a preview card per theme plus "Follow system".
class ThemeSelector extends ConsumerWidget {
  const ThemeSelector({super.key});

  static const _cardWidth = 156.0;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final selected = ref.watch(themePreferenceProvider);
    final theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Theme', style: theme.textTheme.titleSmall),
          const SizedBox(height: 4),
          Text(
            selected == ThemePreference.system
                ? 'Follows your device: Arctic Light by day, Midnight Gold at night'
                : selected.resolve(Brightness.dark).description,
            style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onSurfaceVariant),
          ),
          const SizedBox(height: 12),
          Wrap(
            spacing: 12,
            runSpacing: 12,
            children: [
              for (final option in ThemePreference.values)
                SizedBox(
                  width: _cardWidth,
                  child: _ThemeOption(
                    option: option,
                    selected: option == selected,
                    onTap: () => ref.read(themePreferenceProvider.notifier).set(option),
                  ),
                ),
            ],
          ),
        ],
      ),
    );
  }
}

class _ThemeOption extends StatelessWidget {
  const _ThemeOption({required this.option, required this.selected, required this.onTap});

  final ThemePreference option;
  final bool selected;
  final VoidCallback onTap;

  String get _label => option == ThemePreference.system ? 'Follow system' : option.resolve(Brightness.dark).label;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final radius = BorderRadius.circular(DhanzRadii.control);
    return Semantics(
      button: true,
      selected: selected,
      label: '$_label theme',
      excludeSemantics: true,
      child: Material(
        color: scheme.surfaceContainer,
        shape: RoundedRectangleBorder(
          borderRadius: radius,
          side: BorderSide(color: selected ? scheme.primary : scheme.outlineVariant, width: selected ? 2 : 1),
        ),
        clipBehavior: Clip.antiAlias,
        child: InkWell(
          onTap: onTap,
          child: Padding(
            padding: const EdgeInsets.all(8),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                ClipRRect(
                  borderRadius: BorderRadius.circular(DhanzRadii.chip),
                  child: SizedBox(
                    height: 78,
                    child: option == ThemePreference.system
                        ? const Row(
                            children: [
                              Expanded(child: _MiniPreview(DhanzPalette.arcticLight)),
                              Expanded(child: _MiniPreview(DhanzPalette.midnightGold)),
                            ],
                          )
                        : _MiniPreview(option.resolve(Brightness.dark).palette),
                  ),
                ),
                const SizedBox(height: 8),
                Row(
                  children: [
                    Expanded(
                      child: Text(
                        _label,
                        style: Theme.of(context).textTheme.labelLarge,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                    if (selected) Icon(Icons.check_circle, size: 18, color: scheme.primary),
                  ],
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// A tiny drawing of the chat in [p]'s colours: page, a reply bubble, the user's accent bubble
/// and the composer. Uses the previewed palette on purpose, not the current theme.
class _MiniPreview extends StatelessWidget {
  const _MiniPreview(this.p);

  final DhanzPalette p;

  @override
  Widget build(BuildContext context) {
    Widget line(double width, Color color) => Container(
      width: width,
      height: 5,
      decoration: BoxDecoration(color: color, borderRadius: BorderRadius.circular(3)),
    );
    return ColoredBox(
      color: p.background,
      child: Padding(
        padding: const EdgeInsets.all(8),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Align(
              alignment: Alignment.centerRight,
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 4),
                decoration: BoxDecoration(color: p.accent, borderRadius: BorderRadius.circular(6)),
                child: line(28, p.onAccent),
              ),
            ),
            const SizedBox(height: 5),
            Align(
              alignment: Alignment.centerLeft,
              child: Container(
                padding: const EdgeInsets.all(5),
                decoration: BoxDecoration(
                  color: p.surface,
                  borderRadius: BorderRadius.circular(6),
                  border: Border.all(color: p.outlineVariant),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [line(40, p.text), const SizedBox(height: 3), line(26, p.muted)],
                ),
              ),
            ),
            const Spacer(),
            Container(
              height: 12,
              decoration: BoxDecoration(color: p.surfaceHighest, borderRadius: BorderRadius.circular(6)),
              alignment: Alignment.centerRight,
              padding: const EdgeInsets.all(2),
              child: Container(
                width: 8,
                decoration: BoxDecoration(color: p.secondary, shape: BoxShape.circle),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
