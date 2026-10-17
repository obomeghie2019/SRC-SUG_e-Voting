# Mobile app (Flutter)

Talks only to the **mobile API** (`backend/api_mobile`, port 8002).

Sign-in flow: **turn on location** -> **matric number** -> **choose email or SMS** -> **enter the one-time code** -> ballot.
The code is sent only to the email/phone already stored for the voter. Location, IP and device id are recorded with the vote receipt.

    flutter create .            # one-time: generates android/ ios/ folders next to lib/
    flutter pub get
    flutter run                                        # Android emulator -> http://10.0.2.2:8002
    flutter run --dart-define=API_URL=http://192.168.1.20:8002/api/mobile   # real phone on same Wi-Fi

## Location permissions (required, add after `flutter create .`)

**Android**: in `android/app/src/main/AndroidManifest.xml`, inside `<manifest>` (above `<application>`):

    <uses-permission android:name="android.permission.ACCESS_FINE_LOCATION"/>
    <uses-permission android:name="android.permission.ACCESS_COARSE_LOCATION"/>

**iOS**: in `ios/Runner/Info.plist`, inside the top-level `<dict>`:

    <key>NSLocationWhenInUseUsageDescription</key>
    <string>Voting needs your location to confirm you are in an allowed area.</string>

On the Android emulator set a position first (Extended controls -> Location), or the app cannot read one.

Android release builds need `android:usesCleartextTraffic="true"` only for plain-HTTP testing.
Use HTTPS in production.
