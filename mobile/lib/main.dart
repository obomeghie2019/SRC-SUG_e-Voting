import 'package:flutter/material.dart';
import 'api.dart';
import 'ballot_screen.dart';
import 'login_screen.dart';

void main() => runApp(const VotingApp());

Color parseHex(String? hex, Color fallback) {
  if (hex == null || !RegExp(r'^#[0-9a-fA-F]{6}$').hasMatch(hex)) return fallback;
  return Color(int.parse('FF${hex.substring(1)}', radix: 16));
}

class VotingApp extends StatefulWidget {
  const VotingApp({super.key});
  @override
  State<VotingApp> createState() => _VotingAppState();
}

class _VotingAppState extends State<VotingApp> {
  Map<String, dynamic> cfg = {'institution_name': '', 'election_title': 'e-Voting', 'election_status': 'draft', 'theme_color': '#0b6e4f'};
  bool? signedIn;

  @override
  void initState() {
    super.initState();
    refresh();
  }

  Future<void> refresh() async {
    final t = await Api.token;
    Map<String, dynamic> c = cfg;
    try {
      c = await Api.config();
    } catch (_) {}
    if (mounted) setState(() { cfg = c; signedIn = t != null; });
  }

  @override
  Widget build(BuildContext context) {
    final brand = parseHex(cfg['theme_color'] as String?, const Color(0xFF0B6E4F));
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      title: cfg['election_title'] as String,
      theme: ThemeData(colorScheme: ColorScheme.fromSeed(seedColor: brand), useMaterial3: true),
      home: signedIn == null
          ? const Scaffold(body: Center(child: CircularProgressIndicator()))
          : signedIn!
              ? BallotScreen(cfg: cfg, onSignedOut: () => setState(() => signedIn = false), onRefreshConfig: refresh)
              : LoginScreen(cfg: cfg, onSignedIn: () async { await refresh(); }),
    );
  }
}
