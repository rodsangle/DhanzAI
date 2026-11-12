import 'dart:js_interop';
import 'dart:js_interop_unsafe';

import 'package:web/web.dart' as web;

import 'wake_types.dart';

@JS()
extension type _Recognition._(JSObject _) implements JSObject {
  external set continuous(bool value);
  external set interimResults(bool value);
  external set lang(String value);
  external set onresult(JSFunction? value);
  external set onerror(JSFunction? value);
  external set onend(JSFunction? value);
  external void start();
  external void abort();
}

@JS()
extension type _ResultEvent._(JSObject _) implements JSObject {
  external int get resultIndex;
  external JSArray<_Result> get results;
}

@JS()
extension type _Result._(JSObject _) implements JSObject {
  external bool get isFinal;
  external _Alternative item(int index);
}

@JS()
extension type _Alternative._(JSObject _) implements JSObject {
  external String get transcript;
}

@JS()
extension type _Error._(JSObject _) implements JSObject {
  external String get error;
}

WakeRecognizer createWakeRecognizer() => _BrowserWake();

class _BrowserWake implements WakeRecognizer {
  _Recognition? _recognition;
  JSFunction? get _constructor {
    final window = web.window;
    final value =
        window.getProperty<JSAny?>('SpeechRecognition'.toJS) ??
        window.getProperty<JSAny?>('webkitSpeechRecognition'.toJS);
    return value != null && value.isA<JSFunction>() ? value as JSFunction : null;
  }

  @override
  bool get supported => _constructor != null;
  @override
  void start({
    required void Function(String) onText,
    required void Function(String) onError,
    required void Function() onEnd,
  }) {
    stop();
    final constructor = _constructor;
    if (constructor == null) {
      onError('This browser does not support wake listening. Use the microphone button.');
      return;
    }
    final recognition = _Recognition._(constructor.callAsConstructor<JSObject>());
    _recognition = recognition;
    recognition.continuous = true;
    recognition.interimResults = false;
    recognition.lang = 'en-US';
    recognition.onresult = ((_ResultEvent event) {
      for (var i = event.resultIndex; i < event.results.length; i++) {
        final result = event.results[i];
        if (result.isFinal) onText(result.item(0).transcript);
      }
    }).toJS;
    recognition.onerror = ((_Error event) => onError(event.error)).toJS;
    recognition.onend = (() => onEnd()).toJS;
    recognition.start();
  }

  @override
  void stop() {
    final recognition = _recognition;
    _recognition = null;
    if (recognition == null) return;
    recognition.onresult = null;
    recognition.onerror = null;
    recognition.onend = null;
    recognition.abort();
  }
}
