abstract class WakeRecognizer {
  bool get supported;
  void start({required void Function(String) onText, required void Function(String) onError, required void Function() onEnd});
  void stop();
}
