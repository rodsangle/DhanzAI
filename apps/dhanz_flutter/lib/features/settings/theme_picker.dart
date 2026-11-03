import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/providers.dart';
import '../../core/theme.dart';

/// The previews use the actual theme tokens, independent of the currently selected skin.
class ThemePicker extends ConsumerWidget {
  const ThemePicker({super.key});

  Future<void> _select(BuildContext context, WidgetRef ref, DhanzThemeStyle style) async {
    try {
      await ref.read(themeStyleProvider.notifier).set(style);
    } catch (_) {
      if (context.mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(const SnackBar(content: Text('Theme applied. Could not save it for next time.')));
      }
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final selected = ref.watch(themeStyleProvider);
    final mode = ref.watch(themeModeProvider);
    final scheme = Theme.of(context).colorScheme;
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          LayoutBuilder(
            builder: (context, constraints) {
              final width = constraints.maxWidth >= 560 ? (constraints.maxWidth - 12) / 2 : constraints.maxWidth;
              return Wrap(
                spacing: 12,
                runSpacing: 12,
                children: [
                  for (final style in DhanzThemeStyle.values)
                    SizedBox(
                      width: width,
                      child: Semantics(
                        button: true,
                        selected: selected == style,
                        label: '${style.label} theme. ${style.description}',
                        excludeSemantics: true,
                        onTap: () => _select(context, ref, style),
                        child: Material(
                          color: scheme.surfaceContainer,
                          shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(16),
                            side: BorderSide(
                              color: selected == style ? scheme.primary : scheme.outlineVariant,
                              width: selected == style ? 2 : 1,
                            ),
                          ),
                          clipBehavior: Clip.antiAlias,
                          child: InkWell(
                            key: ValueKey('theme-${style.name}'),
                            excludeFromSemantics: true,
                            onTap: () => _select(context, ref, style),
                            child: Padding(
                              padding: const EdgeInsets.all(14),
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.stretch,
                                children: [
                                  _Preview(style: style, mode: mode),
                                  const SizedBox(height: 12),
                                  Row(
                                    children: [
                                      Expanded(child: Text(style.label, style: Theme.of(context).textTheme.titleSmall)),
                                      Icon(
                                        selected == style ? Icons.check_circle : Icons.circle_outlined,
                                        color: selected == style ? scheme.primary : scheme.onSurfaceVariant,
                                        size: 22,
                                      ),
                                    ],
                                  ),
                                  const SizedBox(height: 4),
                                  Text(style.description, style: Theme.of(context).textTheme.bodySmall),
                                ],
                              ),
                            ),
                          ),
                        ),
                      ),
                    ),
                ],
              );
            },
          ),
          if (selected == DhanzThemeStyle.original) ...[
            const SizedBox(height: 16),
            DropdownButtonFormField<ThemeMode>(
              key: ValueKey(mode),
              initialValue: mode,
              isExpanded: true,
              decoration: const InputDecoration(labelText: 'Original appearance'),
              items: const [
                DropdownMenuItem(value: ThemeMode.dark, child: Text('Dark')),
                DropdownMenuItem(value: ThemeMode.light, child: Text('Light')),
                DropdownMenuItem(value: ThemeMode.system, child: Text('Follow system')),
              ],
              onChanged: (value) async {
                if (value == null) return;
                try {
                  await ref.read(themeModeProvider.notifier).set(value);
                } catch (_) {
                  if (context.mounted) {
                    ScaffoldMessenger.of(context).showSnackBar(
                      const SnackBar(content: Text('Appearance applied. Could not save it for next time.')),
                    );
                  }
                }
              },
            ),
          ],
        ],
      ),
    );
  }
}

class _Preview extends StatelessWidget {
  const _Preview({required this.style, required this.mode});
  final DhanzThemeStyle style;
  final ThemeMode mode;

  @override
  Widget build(BuildContext context) {
    final brightness = style.mode(mode) == ThemeMode.light
        ? Brightness.light
        : style.mode(mode) == ThemeMode.dark
        ? Brightness.dark
        : MediaQuery.platformBrightnessOf(context);
    final colors = style.theme(brightness).colorScheme;
    return SizedBox(
      height: 68,
      child: DecoratedBox(
        decoration: BoxDecoration(color: colors.surface, borderRadius: BorderRadius.circular(10)),
        child: Row(
          children: [
            Container(
              width: 38,
              margin: const EdgeInsets.all(6),
              decoration: BoxDecoration(color: colors.surfaceContainerHigh, borderRadius: BorderRadius.circular(6)),
              child: Icon(Icons.auto_awesome, color: colors.primary, size: 19),
            ),
            Expanded(
              child: Padding(
                padding: const EdgeInsets.all(8),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Align(
                      alignment: Alignment.centerRight,
                      child: Container(
                        width: 90,
                        height: 12,
                        decoration: BoxDecoration(color: colors.primary, borderRadius: BorderRadius.circular(4)),
                      ),
                    ),
                    Container(height: 6, color: colors.onSurface.withValues(alpha: 0.6)),
                    FractionallySizedBox(
                      widthFactor: 0.65,
                      alignment: Alignment.centerLeft,
                      child: Container(height: 6, color: colors.onSurfaceVariant.withValues(alpha: 0.5)),
                    ),
                    Container(height: 12, color: colors.surfaceContainerHigh),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
