import 'dart:math';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';

import '../../core/api/api_client.dart';
import '../../core/providers.dart';
import 'chat_preview.dart';

String excelColumn(int value) {
  var result = '';
  while (value > 0) {
    value--;
    result = String.fromCharCode(65 + value % 26) + result;
    value ~/= 26;
  }
  return result;
}

(int, int, int, int) workbookRange(String value) {
  final match = RegExp(
    r'^([A-Za-z]{1,3})([1-9][0-9]{0,4})(?::([A-Za-z]{1,3})([1-9][0-9]{0,4}))?$',
  ).firstMatch(value.trim());
  if (match == null) {
    throw const FormatException('Use a bounded range such as A1 or G33:AI33.');
  }
  int column(String value) =>
      value.toUpperCase().codeUnits.fold(0, (n, c) => n * 26 + c - 64);
  final a = column(match[1]!),
      b = int.parse(match[2]!),
      c = column(match[3] ?? match[1]!),
      d = int.parse(match[4] ?? match[2]!);
  if (a > c ||
      b > d ||
      c > 256 ||
      d > 20000 ||
      (c - a + 1) * (d - b + 1) > 5000) {
    throw const FormatException(
      'Use at most 5000 cells, 256 columns and 20000 rows.',
    );
  }
  return (a, b, c, d);
}

Object? workbookValue(String text) {
  if (text.isEmpty) {
    return null;
  }
  if (!text.contains('.') && text.replaceAll('-', '').length > 15) {
    return text;
  }
  if (RegExp(r'^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$').hasMatch(text)) {
    final value = num.tryParse(text);
    if (value != null && value.isFinite) {
      return value;
    }
  }
  return text;
}

String workbookDisplay(Map<String, dynamic> cell) {
  final value = cell['value'];
  final format = (cell['format'] as Map?)?['number_format'];
  if (value is num && value.isFinite) {
    if (format == '0.00') {
      return value.toStringAsFixed(2);
    }
    if (format == '0.00%') {
      return '${(value * 100).toStringAsFixed(2)}%';
    }
    if (format == r'$#,##0.00') {
      return NumberFormat.currency(
        symbol: r'$',
        decimalDigits: 2,
      ).format(value);
    }
    if (format == 'yyyy-mm-dd' && value >= 1 && value <= 2958465) {
      return DateFormat('yyyy-MM-dd')
          .format(DateTime(1899, 12, 30).add(Duration(days: value.floor())));
    }
  }
  return '${value ?? ''}';
}

class WorkbookPreview extends ConsumerStatefulWidget {
  const WorkbookPreview({
    super.key,
    required this.documentId,
    required this.filename,
    required this.downloadBuilder,
  });
  final String documentId, filename;
  final Widget Function(String id, String name) downloadBuilder;
  @override
  ConsumerState<WorkbookPreview> createState() => _WorkbookPreviewState();
}

class _WorkbookPreviewState extends ConsumerState<WorkbookPreview> {
  final _range = TextEditingController(text: 'A1');
  final _value = TextEditingController();
  late final TextEditingController _filename;
  final _actions = <Map<String, dynamic>>[];
  int _cursor = 0, _tab = 0, _row = 1, _col = 1;
  double _zoom = 1;
  Map<String, dynamic>? _data;
  String? _error, _sheet, _saveKey;
  bool _loading = true, _saving = false;
  late String _id;
  late final Future<bool> Function() _guard = _confirmDiscard;
  ChatPreviewController? _panel;
  int _loadEpoch = 0;

  @override
  void initState() {
    super.initState();
    _id = widget.documentId;
    _filename = TextEditingController(
      text: widget.filename.startsWith('Edited_')
          ? widget.filename
          : 'Edited_${widget.filename}',
    );
    _load();
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _panel = ChatPreviewScope.of(context);
    _panel?.beforeClose = _guard;
  }

  @override
  void dispose() {
    if (_panel?.beforeClose == _guard) _panel?.beforeClose = null;
    _range.dispose();
    _value.dispose();
    _filename.dispose();
    super.dispose();
  }

  Future<bool> _confirmDiscard() async {
    if (_saving) {
      _snack('Wait for the save result before closing this workbook.');
      return false;
    }
    if (_cursor == 0) {
      return true;
    }
    return await showDialog<bool>(
          context: context,
          builder: (context) => AlertDialog(
            title: const Text('Discard unsaved changes?'),
            content: const Text(
              'Save a copy first to keep these workbook changes.',
            ),
            actions: [
              TextButton(
                onPressed: () => Navigator.pop(context, false),
                child: const Text('Keep editing'),
              ),
              TextButton(
                onPressed: () => Navigator.pop(context, true),
                child: const Text('Discard'),
              ),
            ],
          ),
        ) ??
        false;
  }

  void _snack(String value) {
    if (mounted) {
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text(value)));
    }
  }

  Future<void> _load() async {
    final epoch = ++_loadEpoch;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final endRow = min(_row + 49, 20000), endCol = min(_col + 39, 256);
      final result = await ref
          .read(apiClientProvider)
          .workbookPage(
            _id,
            sheet: _sheet,
            area: '${excelColumn(_col)}$_row:${excelColumn(endCol)}$endRow',
          );
      if (!mounted || epoch != _loadEpoch) {
        return;
      }
      setState(() {
        _data = result;
        _sheet = result['sheet'] as String;
        _loading = false;
      });
    } catch (error) {
      if (!mounted || epoch != _loadEpoch) {
        return;
      }
      setState(() {
        _loading = false;
        _error = error is ApiException && error.statusCode == 404
            ? 'Workbook editing is not available on this server yet. Install the Office preview backend update.'
            : '$error';
      });
    }
  }

  void _stage(Map<String, dynamic> action) {
    if (_saving || _data == null) {
      return;
    }
    try {
      workbookRange(_range.text);
    } on FormatException catch (error) {
      _snack(error.message.toString());
      return;
    }
    if (_cursor >= 40) {
      _snack('Save this copy before adding more than 40 changes.');
      return;
    }
    setState(() {
      _actions.removeRange(_cursor, _actions.length);
      _actions.add({
        'sheet': _sheet,
        'range': _range.text.toUpperCase(),
        ...action,
      });
      _cursor++;
      _saveKey = null;
    });
  }

  void _format(Map<String, dynamic> options) =>
      _stage({'type': 'format_range', 'format': options});

  void _toggle(String property) {
    try {
      final (a, b, _, _) = workbookRange(_range.text);
      final format = _cells()['${excelColumn(a)}$b']?['format'] as Map? ?? {};
      _format({property: format[property] != true});
    } catch (error) {
      _snack('$error');
    }
  }

  void _applyValue() {
    final text = _value.text;
    if (text.startsWith('=')) {
      _stage({'type': 'set_formula', 'formula': text});
      return;
    }
    try {
      final (a, b, c, d) = workbookRange(_range.text);
      final value = workbookValue(text);
      _stage({
        'type': 'set_cells',
        'values': List.generate(
          d - b + 1,
          (_) => List.filled(c - a + 1, value),
        ),
      });
    } on FormatException catch (error) {
      _snack(error.message.toString());
    }
  }

  Map<String, Map<String, dynamic>> _cells() {
    final cells = {
      for (final raw in (_data?['cells'] as List? ?? []))
        (raw as Map)['cell'] as String: Map<String, dynamic>.from(raw),
    };
    for (final action
        in _actions.take(_cursor).where((a) => a['sheet'] == _sheet)) {
      if (action['type'] == 'add_sheet') {
        continue;
      }
      final (a, b, c, d) = workbookRange(action['range'] as String);
      for (var y = b; y <= d; y++) {
        for (var x = a; x <= c; x++) {
          final address = '${excelColumn(x)}$y';
          final cell = cells[address];
          if (cell == null) {
            continue;
          }
          if (action['type'] == 'format_range') {
            cell['format'] = {
              ...?cell['format'] as Map?,
              ...action['format'] as Map,
            };
          } else if (action['type'] == 'set_cells') {
            cell['value'] = (action['values'] as List)[y - b][x - a];
            cell['formula'] = false;
          } else if (action['type'] == 'set_formula') {
            cell['value'] = x == a && y == b
                ? action['formula']
                : 'Formula fill pending';
            cell['formula'] = true;
          }
        }
      }
    }
    return cells;
  }

  Future<void> _copy() async {
    try {
      final (a, b, c, d) = workbookRange(_range.text);
      final cells = _cells();
      if ((c - a + 1) * (d - b + 1) > 500) {
        throw const FormatException('Copy at most 500 visible cells at once.');
      }
      final rows = <String>[];
      for (var y = b; y <= d; y++) {
        final values = <String>[];
        for (var x = a; x <= c; x++) {
          final cell = cells['${excelColumn(x)}$y'];
          if (cell == null) {
            throw const FormatException(
              'Navigate to this range before copying.',
            );
          }
          values.add('${cell['value'] ?? ''}');
        }
        rows.add(values.join('\t'));
      }
      await Clipboard.setData(ClipboardData(text: rows.join('\n')));
      _snack('Copied selected cells.');
    } on FormatException catch (error) {
      _snack(error.message.toString());
    }
  }

  Future<void> _paste() async {
    final sheet = _sheet, range = _range.text;
    final data = await Clipboard.getData(Clipboard.kTextPlain);
    if (!mounted ||
        _saving ||
        sheet != _sheet ||
        range != _range.text ||
        data?.text == null) {
      return;
    }
    try {
      final (a, b, _, _) = workbookRange(range);
      final lines = data!.text!.replaceAll('\r\n', '\n').split('\n');
      if (lines.length > 1 && lines.last.isEmpty) lines.removeLast();
      final values = [for (final row in lines) row.split('\t')];
      final width = values.fold<int>(0, (n, row) => max(n, row.length));
      for (final row in values) {
        while (row.length < width) {
          row.add('');
        }
      }
      final area =
          '${excelColumn(a)}$b:${excelColumn(a + width - 1)}${b + values.length - 1}';
      workbookRange(area);
      final formulas = <Map<String, dynamic>>[];
      for (var y = 0; y < values.length; y++) {
        for (var x = 0; x < width; x++) {
          if (values[y][x].startsWith('=')) {
            formulas.add({
              'type': 'set_formula',
              'range': '${excelColumn(a + x)}${b + y}',
              'formula': values[y][x],
            });
          }
        }
      }
      if (_cursor + 1 + formulas.length > 40) {
        _snack(
          'This paste exceeds the 40-change save limit. Save first or paste fewer formula cells.',
        );
        return;
      }
      _range.text = area;
      _stage({
        'type': 'set_cells',
        'values': [
          for (final row in values)
            [for (final value in row) workbookValue(value)],
        ],
      });
      for (final formula in formulas) {
        _stage(formula);
      }
    } catch (_) {
      _snack('Clipboard cells could not be pasted into this range.');
    }
  }

  Future<void> _addSheet() async {
    final name = await _ask(
      'Add worksheet',
      'Sheet${(_data?['sheets'] as List? ?? []).length + 1}',
    );
    if (name == null || !mounted) {
      return;
    }
    if (name.isEmpty ||
        name.length > 31 ||
        RegExp(r'[\\/*?:\[\]]').hasMatch(name)) {
      _snack('Use a valid worksheet name of at most 31 characters.');
      return;
    }
    _stage({'type': 'add_sheet', 'sheet': name});
    _snack('Worksheet will be added when you save the copy.');
  }

  Future<String?> _ask(String title, String initial) async {
    var value = initial;
    return showDialog<String>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(title),
        content: TextFormField(
          initialValue: initial,
          onChanged: (text) => value = text,
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, value),
            child: const Text('Apply'),
          ),
        ],
      ),
    );
  }

  Future<void> _dimension(bool column) async {
    final value = await _ask(
      column ? 'Column width' : 'Row height',
      column ? '20' : '24',
    );
    if (value == null || !mounted) {
      return;
    }
    final number = double.tryParse(value);
    if (number == null || !number.isFinite || number < 1 || number > 200) {
      _snack('Use a size from 1 to 200.');
      return;
    }
    _format({column ? 'column_width' : 'row_height': number});
  }

  Future<void> _save() async {
    if (_saving || _cursor == 0) {
      return;
    }
    if (!_filename.text.toLowerCase().endsWith('.xlsx')) {
      _snack('Use an .xlsx filename.');
      return;
    }
    final id = _id;
    _saveKey ??= List.generate(
      16,
      (_) => Random.secure().nextInt(256).toRadixString(16).padLeft(2, '0'),
    ).join();
    final actions = [
      for (final action in _actions.take(_cursor))
        Map<String, dynamic>.from(action),
    ];
    setState(() => _saving = true);
    try {
      final result = await ref
          .read(apiClientProvider)
          .saveWorkbook(id, _saveKey!, _filename.text, actions);
      if (!mounted) {
        return;
      }
      setState(() {
        _id = result['id'] as String;
        _filename.text = result['filename'] as String;
        _actions.clear();
        _cursor = 0;
        _saveKey = null;
      });
      _snack('Workbook copy saved. Original preserved.');
      setState(() => _saving = false);
      if (_panel != null) {
        _panel!.replaceTarget(
          ChatPreviewTarget(documentId: _id, filename: _filename.text),
        );
      } else {
        await _load();
      }
    } catch (error) {
      _snack(
        'Save not confirmed: $error. Retry Save copy explicitly; the same save key will be reused.',
      );
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  Widget _tool(String label, IconData icon, VoidCallback action) =>
      TextButton.icon(
        onPressed: _saving || _loading || _data == null ? null : action,
        icon: Icon(icon, size: 17),
        label: Text(label),
      );

  @override
  Widget build(BuildContext context) {
    final theme = ThemeData(
      useMaterial3: true,
      colorScheme: ColorScheme.fromSeed(
        seedColor: const Color(0xff217346),
        brightness: Brightness.light,
      ),
    );
    return Theme(
      data: theme,
      child: Material(
        color: const Color(0xfff3f3f3),
        child: Column(
          children: [
            Container(
              color: const Color(0xff217346),
              padding: const EdgeInsets.all(8),
              child: Row(
                children: [
                  const Icon(Icons.table_chart, color: Colors.white),
                  const SizedBox(width: 8),
                  const Expanded(
                    child: Text(
                      'Workbook',
                      style: TextStyle(
                        color: Colors.white,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                  ),
                  TextButton(
                    onPressed: _cursor > 0 && !_saving ? _save : null,
                    style: TextButton.styleFrom(foregroundColor: Colors.white),
                    child: Text(_saving ? 'Saving…' : 'Save copy ($_cursor)'),
                  ),
                ],
              ),
            ),
            SizedBox(
              height: 38,
              child: ListView(
                scrollDirection: Axis.horizontal,
                children: [
                  for (var i = 0; i < 4; i++)
                    TextButton(
                      onPressed: () => setState(() => _tab = i),
                      child: Text(
                        ['Home', 'Insert', 'Formulas', 'View'][i],
                        style: TextStyle(
                          fontWeight: _tab == i
                              ? FontWeight.bold
                              : FontWeight.normal,
                        ),
                      ),
                    ),
                ],
              ),
            ),
            SizedBox(
              height: 48,
              child: SingleChildScrollView(
                scrollDirection: Axis.horizontal,
                child: Row(
                  children: _tab == 0
                      ? [
                          _tool(
                            'Undo',
                            Icons.undo,
                            () => setState(() {
                              if (_cursor > 0) _cursor--;
                              _saveKey = null;
                            }),
                          ),
                          _tool(
                            'Redo',
                            Icons.redo,
                            () => setState(() {
                              if (_cursor < _actions.length) _cursor++;
                              _saveKey = null;
                            }),
                          ),
                          _tool('Copy', Icons.copy, _copy),
                          _tool('Paste', Icons.paste, _paste),
                          _tool(
                            'Bold',
                            Icons.format_bold,
                            () => _toggle('bold'),
                          ),
                          _tool(
                            'Unbold',
                            Icons.format_clear,
                            () => _format({'bold': false}),
                          ),
                          _tool(
                            'Italic',
                            Icons.format_italic,
                            () => _toggle('italic'),
                          ),
                          _tool(
                            'Borders',
                            Icons.border_all,
                            () => _format({'border': true}),
                          ),
                          _tool(
                            'No borders',
                            Icons.border_clear,
                            () => _format({'border': false}),
                          ),
                          _tool(
                            'Wrap',
                            Icons.wrap_text,
                            () => _toggle('wrap_text'),
                          ),
                          _tool(
                            'Left',
                            Icons.format_align_left,
                            () => _format({'horizontal': 'left'}),
                          ),
                          _tool(
                            'Center',
                            Icons.format_align_center,
                            () => _format({'horizontal': 'center'}),
                          ),
                          _tool(
                            'Right',
                            Icons.format_align_right,
                            () => _format({'horizontal': 'right'}),
                          ),
                          PopupMenuButton<String>(
                            tooltip: 'Text color',
                            onSelected: (value) =>
                                _format({'font_color': value}),
                            itemBuilder: (_) => [
                              for (final color in {
                                'Black': '000000',
                                'White': 'FFFFFF',
                                'Green': '217346',
                                'Red': 'C00000',
                                'Blue': '0070C0',
                              }.entries)
                                PopupMenuItem(
                                  value: color.value,
                                  child: Text(color.key),
                                ),
                            ],
                            child: const Padding(
                              padding: EdgeInsets.all(12),
                              child: Text('Font color ▾'),
                            ),
                          ),
                          PopupMenuButton<double>(
                            tooltip: 'Font size',
                            onSelected: (value) =>
                                _format({'font_size': value}),
                            itemBuilder: (_) => [
                              for (final size in [
                                10.0,
                                11.0,
                                12.0,
                                14.0,
                                16.0,
                                18.0,
                                24.0,
                                36.0,
                              ])
                                PopupMenuItem(
                                  value: size,
                                  child: Text('${size.round()} pt'),
                                ),
                            ],
                            child: const Padding(
                              padding: EdgeInsets.all(12),
                              child: Text('Size ▾'),
                            ),
                          ),
                          _tool(
                            'Underline',
                            Icons.format_underline,
                            () => _toggle('underline'),
                          ),
                          PopupMenuButton<String>(
                            tooltip: 'Fill color',
                            onSelected: (value) =>
                                _format({'fill_color': value}),
                            itemBuilder: (_) => [
                              for (final color in {
                                'Yellow': 'FFF2CC',
                                'Green': 'E2EFDA',
                                'Blue': 'DDEBF7',
                                'White': 'FFFFFF',
                              }.entries)
                                PopupMenuItem(
                                  value: color.value,
                                  child: Text(color.key),
                                ),
                            ],
                            child: const Padding(
                              padding: EdgeInsets.all(12),
                              child: Text('Fill ▾'),
                            ),
                          ),
                          PopupMenuButton<String>(
                            tooltip: 'Number format',
                            onSelected: (value) =>
                                _format({'number_format': value}),
                            itemBuilder: (_) => [
                              for (final f in {
                                'General': 'General',
                                'Number': '0.00',
                                'Currency': r'$#,##0.00',
                                'Percent': '0.00%',
                                'Date': 'yyyy-mm-dd',
                                'Text': '@',
                              }.entries)
                                PopupMenuItem(
                                  value: f.value,
                                  child: Text(f.key),
                                ),
                            ],
                            child: const Padding(
                              padding: EdgeInsets.all(12),
                              child: Text('Number ▾'),
                            ),
                          ),
                          _tool(
                            'Column width',
                            Icons.width_normal,
                            () => _dimension(true),
                          ),
                          _tool(
                            'Row height',
                            Icons.height,
                            () => _dimension(false),
                          ),
                        ]
                      : _tab == 1
                      ? [
                          _tool(
                            'Add worksheet',
                            Icons.add_box_outlined,
                            _addSheet,
                          ),
                        ]
                      : _tab == 2
                      ? [
                          _tool('AutoSum', Icons.functions, () {
                            try {
                              final (a, b, _, _) = workbookRange(_range.text);
                              if (b < 2) {
                                _snack('Select a totals cell below row 1.');
                                return;
                              }
                              _value.text =
                                  '=SUM(${excelColumn(a)}1:${excelColumn(a)}${b - 1})';
                            } catch (error) {
                              _snack('$error');
                            }
                          }),
                          const Padding(
                            padding: EdgeInsets.all(8),
                            child: Text('Enter a formula below, then Apply.'),
                          ),
                        ]
                      : [
                          _tool(
                            'Freeze header',
                            Icons.view_headline,
                            () =>
                                _stage({'type': 'freeze_panes', 'range': 'A2'}),
                          ),
                          _tool(
                            'Filter range',
                            Icons.filter_alt_outlined,
                            () => _stage({'type': 'auto_filter'}),
                          ),
                          for (final zoom in [0.8, 1.0, 1.25, 1.5])
                            TextButton(
                              onPressed: () => setState(() => _zoom = zoom),
                              child: Text('${(zoom * 100).round()}%'),
                            ),
                        ],
                ),
              ),
            ),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 8),
              child: Row(
                children: [
                  SizedBox(
                    width: 110,
                    child: TextField(
                      controller: _range,
                      decoration: const InputDecoration(
                        labelText: 'Cell / range',
                        isDense: true,
                      ),
                      onSubmitted: (_) => _jump(),
                    ),
                  ),
                  const Padding(
                    padding: EdgeInsets.symmetric(horizontal: 8),
                    child: Text(
                      'fx',
                      style: TextStyle(fontStyle: FontStyle.italic),
                    ),
                  ),
                  Expanded(
                    child: TextField(
                      controller: _value,
                      decoration: const InputDecoration(
                        labelText: 'Value or formula',
                        isDense: true,
                      ),
                      onSubmitted: (_) => _applyValue(),
                    ),
                  ),
                  IconButton(
                    tooltip: 'Apply value or formula',
                    onPressed: _saving ? null : _applyValue,
                    icon: const Icon(Icons.check),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 6),
            if (_error != null)
              Expanded(
                child: Center(
                  child: Padding(
                    padding: const EdgeInsets.all(16),
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Text(_error!),
                        TextButton(
                          onPressed: _load,
                          child: const Text('Retry'),
                        ),
                      ],
                    ),
                  ),
                ),
              )
            else if (_loading)
              const Expanded(child: Center(child: CircularProgressIndicator()))
            else
              Expanded(child: _grid()),
            SizedBox(
              height: 38,
              child: ListView(
                scrollDirection: Axis.horizontal,
                children: [
                  for (final sheet in (_data?['sheets'] as List? ?? []))
                    TextButton(
                      onPressed: _saving
                          ? null
                          : () {
                              setState(() {
                                _sheet = sheet as String;
                                _row = 1;
                                _col = 1;
                              });
                              _load();
                            },
                      child: Text(
                        '$sheet',
                        style: TextStyle(
                          fontWeight: _sheet == sheet
                              ? FontWeight.bold
                              : FontWeight.normal,
                        ),
                      ),
                    ),
                ],
              ),
            ),
            Wrap(
              alignment: WrapAlignment.center,
              children: [
                _tool('Previous rows', Icons.arrow_upward, () {
                  _row = max(1, _row - 50);
                  _load();
                }),
                _tool('Next rows', Icons.arrow_downward, () {
                  _row = min(19951, _row + 50);
                  _load();
                }),
                _tool('Previous columns', Icons.chevron_left, () {
                  _col = max(1, _col - 40);
                  _load();
                }),
                _tool('Next columns', Icons.chevron_right, () {
                  _col = min(217, _col + 40);
                  _load();
                }),
              ],
            ),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 8),
              child: TextField(
                controller: _filename,
                enabled: !_saving,
                decoration: const InputDecoration(
                  labelText: 'Save copy as',
                  isDense: true,
                ),
                onChanged: (_) => _saveKey = null,
              ),
            ),
            Padding(
              padding: const EdgeInsets.all(8),
              child: Row(
                children: [
                  Expanded(
                    child: Text(
                      _cursor == 0
                          ? 'Original preserved · formulas recalculate in Excel'
                          : '$_cursor unsaved changes · save before leaving',
                      style: const TextStyle(fontSize: 11),
                    ),
                  ),
                  widget.downloadBuilder(
                    _id,
                    _data?['filename'] as String? ?? widget.filename,
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  void _jump() {
    try {
      final (a, b, _, _) = workbookRange(_range.text);
      _col = ((a - 1) ~/ 40) * 40 + 1;
      _row = ((b - 1) ~/ 50) * 50 + 1;
      _load();
    } on FormatException catch (error) {
      _snack(error.message.toString());
    }
  }

  Widget _grid() {
    final cells = _cells();
    final widths = Map<String, dynamic>.from(_data?['widths'] as Map? ?? {});
    final heights = Map<String, dynamic>.from(_data?['heights'] as Map? ?? {});
    for (final action in _actions.take(_cursor)) {
      if (action['sheet'] != _sheet || action['type'] != 'format_range') {
        continue;
      }
      final options = action['format'] as Map;
      final (a, b, c, d) = workbookRange(action['range'] as String);
      if (options['column_width'] != null) {
        for (var x = a; x <= c; x++) {
          widths[excelColumn(x)] = options['column_width'];
        }
      }
      if (options['row_height'] != null) {
        for (var y = b; y <= d; y++) {
          heights['$y'] = options['row_height'];
        }
      }
    }
    final endCol = min(_col + 39, 256), endRow = min(_row + 49, 20000);
    (int, int, int, int)? selection;
    try {
      selection = workbookRange(_range.text);
    } catch (_) {}
    return ColoredBox(
      color: Colors.white,
      child: SingleChildScrollView(
        child: SingleChildScrollView(
          scrollDirection: Axis.horizontal,
          child: Table(
            defaultColumnWidth: FixedColumnWidth(110 * _zoom),
            columnWidths: {
              0: FixedColumnWidth(44 * _zoom),
              for (var x = _col; x <= endCol; x++)
                x - _col + 1: FixedColumnWidth(
                  (((widths[excelColumn(x)] as num?)?.toDouble() ?? 13) *
                          7 *
                          _zoom)
                      .clamp(50.0, 600.0)
                      .toDouble(),
                ),
            },
            border: TableBorder.all(color: const Color(0xffdedede), width: 0.5),
            children: [
              TableRow(
                decoration: const BoxDecoration(color: Color(0xffededed)),
                children: [
                  const Text(''),
                  for (var x = _col; x <= endCol; x++)
                    Padding(
                      padding: const EdgeInsets.all(5),
                      child: Text(excelColumn(x), textAlign: TextAlign.center),
                    ),
                ],
              ),
              for (var y = _row; y <= endRow; y++)
                TableRow(
                  children: [
                    Padding(
                      padding: const EdgeInsets.all(6),
                      child: Text(
                        '$y',
                        textAlign: TextAlign.center,
                        style: const TextStyle(color: Colors.grey),
                      ),
                    ),
                    for (var x = _col; x <= endCol; x++)
                      Builder(
                        builder: (context) {
                          final address = '${excelColumn(x)}$y';
                          final cell = cells[address] ?? {};
                          final format = cell['format'] as Map? ?? {};
                          final selected =
                              selection != null &&
                              x >= selection.$1 &&
                              x <= selection.$3 &&
                              y >= selection.$2 &&
                              y <= selection.$4;
                          Color? color(dynamic value) {
                            if (value is! String ||
                                !RegExp(r'^[A-Fa-f0-9]{6}$').hasMatch(value)) {
                              return null;
                            }
                            return Color(int.parse('FF$value', radix: 16));
                          }

                          return InkWell(
                            onTap: () {
                              setState(() {
                                if (HardwareKeyboard.instance.isShiftPressed) {
                                  final (a, b, _, _) = workbookRange(
                                    _range.text,
                                  );
                                  _range.text =
                                      '${excelColumn(min(a, x))}${min(b, y)}:${excelColumn(max(a, x))}${max(b, y)}';
                                } else {
                                  _range.text = address;
                                }
                                _value.text = '${cell['value'] ?? ''}';
                              });
                            },
                            child: Container(
                              constraints: BoxConstraints(
                                minHeight:
                                    (((heights['$y'] as num?)?.toDouble() ??
                                                15) *
                                            1.333 *
                                            _zoom)
                                        .clamp(24.0, 300.0)
                                        .toDouble(),
                              ),
                              padding: const EdgeInsets.all(5),
                              decoration: BoxDecoration(
                                color: selected
                                    ? const Color(0xffd8eadf)
                                    : color(format['fill_color']),
                                border: format['border'] == true
                                    ? Border.all(color: Colors.grey)
                                    : null,
                              ),
                              child: Text(
                                workbookDisplay(
                                  Map<String, dynamic>.from(cell),
                                ),
                                maxLines: format['wrap_text'] == true ? 5 : 1,
                                overflow: TextOverflow.ellipsis,
                                textAlign: switch (format['horizontal']) {
                                  'center' => TextAlign.center,
                                  'right' => TextAlign.right,
                                  _ => TextAlign.left,
                                },
                                style: TextStyle(
                                  fontSize:
                                      ((format['font_size'] as num?)
                                              ?.toDouble() ??
                                          12) *
                                      _zoom,
                                  decoration: format['underline'] == true
                                      ? TextDecoration.underline
                                      : TextDecoration.none,
                                  color:
                                      color(format['font_color']) ??
                                      Colors.black,
                                  fontWeight: format['bold'] == true
                                      ? FontWeight.bold
                                      : FontWeight.normal,
                                  fontStyle: format['italic'] == true
                                      ? FontStyle.italic
                                      : FontStyle.normal,
                                ),
                              ),
                            ),
                          );
                        },
                      ),
                  ],
                ),
            ],
          ),
        ),
      ),
    );
  }
}
