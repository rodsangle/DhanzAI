const runningWebVersion = String.fromEnvironment(
  'DHANZ_WEB_VERSION',
  defaultValue: '0.10.1',
);
const runningWebBuild = int.fromEnvironment(
  'DHANZ_WEB_BUILD',
  defaultValue: 32,
);

typedef WebBuild = ({String version, int build});

int compareWebBuilds(WebBuild a, WebBuild b) {
  List<int> parts(WebBuild item) {
    if (!RegExp(r'^\d+\.\d+\.\d+$').hasMatch(item.version) || item.build < 0) {
      throw const FormatException('Invalid web version');
    }
    return [...item.version.split('.').map(int.parse), item.build];
  }

  final x = parts(a), y = parts(b);
  for (var i = 0; i < x.length; i++) {
    if (x[i] != y[i]) return x[i].compareTo(y[i]);
  }
  return 0;
}

abstract class WebUpdateRuntime {
  Future<WebBuild> servedBuild();
  Future<void> refresh(WebBuild minimum);
}
