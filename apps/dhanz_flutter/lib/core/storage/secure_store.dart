import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// Key-value storage for tokens and settings.
///
/// Backed by the Keychain on iOS/macOS, the Android Keystore, and DPAPI on Windows.
abstract class SecureStore {
  Future<String?> read(String key);
  Future<void> write(String key, String? value);
  Future<void> deleteAll();
}

class FlutterSecureStore implements SecureStore {
  FlutterSecureStore() : _storage = const FlutterSecureStorage();

  final FlutterSecureStorage _storage;

  @override
  Future<String?> read(String key) => _storage.read(key: key);

  @override
  Future<void> write(String key, String? value) =>
      value == null ? _storage.delete(key: key) : _storage.write(key: key, value: value);

  @override
  Future<void> deleteAll() => _storage.deleteAll();
}

/// In-memory store for tests.
class MemorySecureStore implements SecureStore {
  final Map<String, String> values = {};

  @override
  Future<String?> read(String key) async => values[key];

  @override
  Future<void> write(String key, String? value) async {
    if (value == null) {
      values.remove(key);
    } else {
      values[key] = value;
    }
  }

  @override
  Future<void> deleteAll() async => values.clear();
}

abstract final class StoreKeys {
  static const accessToken = 'access_token';
  static const refreshToken = 'refresh_token';
  static const apiUrl = 'api_url';
  static const themeMode = 'theme_mode';
}
