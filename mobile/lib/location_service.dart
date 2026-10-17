import 'package:geolocator/geolocator.dart';

/// Thrown when the position cannot be read. [message] is safe to show to the voter.
class LocationException implements Exception {
  final String message;
  final bool servicesOff; // GPS / location services switched off on the phone
  final bool permanentlyDenied; // user chose "Don't ask again"
  LocationException(this.message, {this.servicesOff = false, this.permanentlyDenied = false});
  @override
  String toString() => message;
}

class LocationService {
  /// Asks for permission if needed and returns {latitude, longitude, accuracy_m}.
  static Future<Map<String, double>> current() async {
    if (!await Geolocator.isLocationServiceEnabled()) {
      throw LocationException('Location (GPS) is turned off on your phone. Turn it ON and try again.', servicesOff: true);
    }
    var perm = await Geolocator.checkPermission();
    if (perm == LocationPermission.denied) perm = await Geolocator.requestPermission();
    if (perm == LocationPermission.denied) {
      throw LocationException('Location permission was denied. Allow it to continue voting.');
    }
    if (perm == LocationPermission.deniedForever) {
      throw LocationException('Location permission is blocked. Open app settings and allow Location.', permanentlyDenied: true);
    }
    try {
      final p = await Geolocator.getCurrentPosition(
        locationSettings: const LocationSettings(accuracy: LocationAccuracy.high, timeLimit: Duration(seconds: 15)),
      );
      return {'latitude': p.latitude, 'longitude': p.longitude, 'accuracy_m': p.accuracy};
    } catch (_) {
      throw LocationException('Could not read your location. Move to an open area and try again.');
    }
  }

  static Future<bool> openLocationSettings() => Geolocator.openLocationSettings();
  static Future<bool> openAppSettings() => Geolocator.openAppSettings();
}
