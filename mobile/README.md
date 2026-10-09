# Mobile app (Flutter)

Talks only to the **mobile API** (`backend/api_mobile`, port 8002).

    flutter create .            # one-time: generates android/ ios/ folders next to lib/
    flutter pub get
    flutter run                                        # Android emulator -> http://10.0.2.2:8002
    flutter run --dart-define=API_URL=http://192.168.1.20:8002/api/mobile   # real phone on same Wi-Fi

Android release builds need `android:usesCleartextTraffic="true"` only for plain-HTTP testing.
Use HTTPS in production.
