import 'wake_types.dart';
WakeRecognizer createWakeRecognizer() => _Unavailable();
class _Unavailable implements WakeRecognizer {
  @override
  bool get supported => false;
  @override
  void start({required void Function(String) onText, required void Function(String) onError, required void Function() onEnd}) {
    onError('Browser wake listening is unavailable here. Use the microphone button.');
  }
  @override
  void stop() {}
}
