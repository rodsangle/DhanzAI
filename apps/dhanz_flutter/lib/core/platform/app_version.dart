import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter/foundation.dart';

import 'web_runtime_types.dart';

import 'package:package_info_plus/package_info_plus.dart';

/// The installed app's version ("0.4.0"), from the platform package metadata.
final appVersionProvider = FutureProvider<String>(
  (ref) async => kIsWeb ? runningWebVersion : (await PackageInfo.fromPlatform()).version,
);
