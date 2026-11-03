# Dhanz appearance themes

`dhanz-theme-concepts.png` compares Midnight Gold, Arctic Light and Aurora Teal.
The image is a generated design mockup, not a screenshot of deployed software.

Midnight Gold, Arctic Light and Aurora Teal are now implemented as selectable
Flutter themes under **Settings → Appearance**, with previews and saved selection.
**Original Dhanz** preserves the previous light/dark/system preference. The new
**Follow system** choice uses Arctic Light for light mode and Midnight Gold for
dark mode. Existing installations keep their original appearance until a theme
is selected; no settings or account data are reset.

| Theme | Background | Surface | Accent | Text |
|---|---|---|---|---|
| Midnight Gold | `#0B1020` | `#182033` | `#E6BD63` | `#F3F4F6` |
| Arctic Light | `#F7FAFF` | `#FFFFFF` | `#176BFF` | `#14213D` |
| Aurora Teal | `#062B33` | `#103F49` | `#65E8CF` | `#EDFFFA` |

Colors are shared through Material ThemeData and ColorScheme across app screens,
dialogs, inputs, navigation, Markdown/code backgrounds and voice accents. The Dhanz
brand logo keeps its original gold identity. Semantic errors keep error colors.

See [setup and verification](../THEMES_AND_SKILLS.md). Running clients must be
updated to see the picker; these source changes do not deploy dhanzai.com.
`claude-theme-prompt.md` records the original implementation brief.
