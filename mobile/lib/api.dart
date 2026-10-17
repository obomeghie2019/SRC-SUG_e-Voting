import 'dart:convert';
import 'dart:math';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:http/http.dart' as http;

/// The mobile app talks ONLY to the mobile API folder (/api/mobile).
/// Android emulator reaches the host machine at 10.0.2.2. For a real phone or production build:
///   flutter run --dart-define=API_URL=https://vote-mobile-api.example.edu.ng/api/mobile
const String apiBase = String.fromEnvironment('API_URL', defaultValue: 'http://10.0.2.2:8002/api/mobile');

class ApiException implements Exception {
  final int status;
  final String message;
  ApiException(this.status, this.message);
  @override
  String toString() => message;
}

class Api {
  /// Uploaded images are stored as "/uploads/<name>"; prefix them with this app's API base. Full URLs pass through.
  static String? assetUrl(String? u) {
    if (u == null || u.isEmpty) return null;
    return u.startsWith('/uploads/') ? '$apiBase$u' : u;
  }

  static const _store = FlutterSecureStorage();
  static const _tokenKey = 'jwt';
  static const _deviceKey = 'device_id';

  static Future<String?> get token => _store.read(key: _tokenKey);
  static Future<void> logout() => _store.delete(key: _tokenKey);

  static Future<String> _deviceId() async {
    var id = await _store.read(key: _deviceKey);
    if (id == null) {
      final r = Random.secure();
      id = List.generate(16, (_) => r.nextInt(256).toRadixString(16).padLeft(2, '0')).join();
      await _store.write(key: _deviceKey, value: id);
    }
    return id;
  }

  static Future<Map<String, String>> _headers({bool auth = false}) async {
    final h = {'Content-Type': 'application/json'};
    if (auth) h['Authorization'] = 'Bearer ${await token}';
    return h;
  }

  static dynamic _handle(http.Response r) {
    final body = r.body.isEmpty ? null : jsonDecode(r.body);
    if (r.statusCode >= 200 && r.statusCode < 300) return body;
    final detail = body is Map && body['detail'] is String ? body['detail'] as String : 'Request failed (${r.statusCode})';
    throw ApiException(r.statusCode, detail);
  }

  static Future<T> _guard<T>(Future<T> Function() fn) async {
    try {
      return await fn();
    } on ApiException {
      rethrow;
    } catch (_) {
      throw ApiException(0, 'Cannot reach the server. Check your connection.');
    }
  }

  /// Institution name, election title, colour and status. Set by the admin dashboard.
  static Future<Map<String, dynamic>> config() => _guard(() async =>
      _handle(await http.get(Uri.parse('$apiBase/config'), headers: await _headers())));

  /// Step 1: matric number + location. Returns {session_id, channels:[{channel, masked}], otp_ttl_minutes}.
  static Future<Map<String, dynamic>> lookup(String matricNo, Map<String, double> where) => _guard(() async {
        final r = await http.post(Uri.parse('$apiBase/auth/lookup'),
            headers: await _headers(),
            body: jsonEncode({'matric_no': matricNo, 'device_id': await _deviceId(), ...where}));
        return _handle(r) as Map<String, dynamic>;
      });

  /// Step 2: send the one-time code by 'email' or 'sms' to the contact already on record.
  static Future<Map<String, dynamic>> sendCode(String sessionId, String channel) => _guard(() async {
        final r = await http.post(Uri.parse('$apiBase/auth/otp/send'),
            headers: await _headers(), body: jsonEncode({'session_id': sessionId, 'channel': channel}));
        return _handle(r) as Map<String, dynamic>;
      });

  /// Step 3: check the code against this session. On success the voting token is stored securely.
  static Future<void> verifyCode(String sessionId, String otp, Map<String, double>? where) => _guard(() async {
        final r = await http.post(Uri.parse('$apiBase/auth/otp/verify'),
            headers: await _headers(), body: jsonEncode({'session_id': sessionId, 'otp': otp, ...?where}));
        final data = _handle(r) as Map<String, dynamic>;
        await _store.write(key: _tokenKey, value: data['token'] as String);
      });

  static Future<Map<String, dynamic>> ballot() => _guard(() async {
        final r = await http.get(Uri.parse('$apiBase/ballot'), headers: await _headers(auth: true));
        if (r.statusCode == 401) await logout();
        return _handle(r) as Map<String, dynamic>;
      });

  static Future<String> vote(Map<int, int> selections, [Map<String, double>? where]) => _guard(() async {
        final body = jsonEncode({'selections': selections.map((k, v) => MapEntry(k.toString(), v)), ...?where});
        final r = await http.post(Uri.parse('$apiBase/vote'), headers: await _headers(auth: true), body: body);
        return (_handle(r) as Map<String, dynamic>)['receipt_code'] as String;
      });
}
