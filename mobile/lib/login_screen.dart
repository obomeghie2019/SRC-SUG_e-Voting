import 'dart:async';
import 'package:flutter/material.dart';
import 'api.dart';
import 'location_service.dart';

enum _Step { location, matric, channel, code }

/// Sign-in: 1) turn on location  2) matric number  3) pick email or SMS  4) enter the one-time code.
class LoginScreen extends StatefulWidget {
  final Map<String, dynamic> cfg;
  final Future<void> Function() onSignedIn;
  const LoginScreen({super.key, required this.cfg, required this.onSignedIn});
  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> with WidgetsBindingObserver {
  final matric = TextEditingController();
  final codeCtl = TextEditingController();
  _Step step = _Step.location;
  Map<String, double>? where;
  Map<String, dynamic>? session;
  String? channel;
  String? sentTo;
  String? error;
  String? locationError;
  bool locationBlocked = false;
  bool servicesOff = false;
  bool busy = false;
  int secondsLeft = 0;
  int resendIn = 0;
  Timer? timer;

  bool get locationRequired => widget.cfg['location_required'] != false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    if (locationRequired) {
      askLocation();
    } else {
      step = _Step.matric;
    }
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    timer?.cancel();
    matric.dispose();
    codeCtl.dispose();
    super.dispose();
  }

  // When the voter comes back from the phone's settings screen, check location again automatically.
  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed && step == _Step.location && !busy) askLocation();
  }

  void startTimer() {
    timer?.cancel();
    timer = Timer.periodic(const Duration(seconds: 1), (_) {
      if (!mounted) return;
      setState(() {
        if (secondsLeft > 0) secondsLeft--;
        if (resendIn > 0) resendIn--;
      });
    });
  }

  Future<void> askLocation() async {
    setState(() { busy = true; locationError = null; });
    try {
      final p = await LocationService.current();
      if (mounted) setState(() { where = p; step = _Step.matric; });
    } on LocationException catch (e) {
      if (mounted) setState(() { locationError = e.message; locationBlocked = e.permanentlyDenied; servicesOff = e.servicesOff; });
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  Future<Map<String, double>?> freshLocation() async {
    try {
      return await LocationService.current();
    } on LocationException {
      return where;
    }
  }

  Future<void> lookup() async {
    setState(() { busy = true; error = null; });
    try {
      final loc = await freshLocation();
      if (loc == null && locationRequired) {
        setState(() => step = _Step.location);
        return;
      }
      where = loc;
      final data = await Api.lookup(matric.text.trim(), loc ?? {});
      final channels = (data['channels'] as List).cast<Map<String, dynamic>>();
      setState(() {
        session = data;
        channel = channels.length == 1 ? channels.first['channel'] as String : null;
        step = _Step.channel;
      });
    } on ApiException catch (e) {
      setState(() => error = e.message);
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  Future<void> sendCode() async {
    setState(() { busy = true; error = null; });
    try {
      final data = await Api.sendCode(session!['session_id'] as String, channel!);
      codeCtl.clear();
      setState(() {
        sentTo = data['sent_to'] as String;
        secondsLeft = data['expires_in_seconds'] as int;
        resendIn = 30;
        step = _Step.code;
      });
      startTimer();
    } on ApiException catch (e) {
      setState(() => error = e.message);
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  Future<void> verify() async {
    setState(() { busy = true; error = null; });
    try {
      final loc = await freshLocation();
      await Api.verifyCode(session!['session_id'] as String, codeCtl.text.trim(), loc);
      await widget.onSignedIn();
    } on ApiException catch (e) {
      setState(() {
        error = e.message;
        if (e.status == 409 || e.status == 410) step = _Step.channel; // expired, locked or replaced
      });
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  String mmss(int s) => '${(s ~/ 60).toString().padLeft(2, '0')}:${(s % 60).toString().padLeft(2, '0')}';

  Widget body(BuildContext context) {
    switch (step) {
      case _Step.location:
        return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          Text('Turn on your location', style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 8),
          const Text('Voting needs your location to confirm you are voting from an allowed place. Choose Allow when asked.'),
          if (locationError != null) Padding(padding: const EdgeInsets.only(top: 12), child: Text(locationError!, style: TextStyle(color: Theme.of(context).colorScheme.error))),
          const SizedBox(height: 16),
          FilledButton(onPressed: busy ? null : askLocation, child: Padding(padding: const EdgeInsets.all(12), child: Text(busy ? 'Checking location' : 'Turn on location'))),
          if (servicesOff) TextButton(onPressed: LocationService.openLocationSettings, child: const Text('Open location settings')),
          if (locationBlocked) TextButton(onPressed: LocationService.openAppSettings, child: const Text('Open app settings')),
        ]);
      case _Step.matric:
        return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          if (where != null) Padding(padding: const EdgeInsets.only(bottom: 12), child: Text('Location is on', style: TextStyle(color: Colors.green.shade700))),
          TextField(controller: matric, decoration: const InputDecoration(labelText: 'Matric number', border: OutlineInputBorder()), textInputAction: TextInputAction.done, onSubmitted: (_) => lookup()),
          const SizedBox(height: 16),
          FilledButton(onPressed: busy ? null : lookup, child: Padding(padding: const EdgeInsets.all(12), child: Text(busy ? 'Checking' : 'Continue'))),
        ]);
      case _Step.channel:
        final channels = (session!['channels'] as List).cast<Map<String, dynamic>>();
        return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          const Text('Where should we send your one-time code? It goes only to the contact already on record for you.'),
          const SizedBox(height: 8),
          for (final c in channels)
            Card(
              child: ListTile(
                leading: Icon(channel == c['channel'] ? Icons.radio_button_checked : Icons.radio_button_unchecked),
                title: Text(c['channel'] == 'email' ? 'Email' : 'SMS'),
                subtitle: Text(c['masked'] as String),
                onTap: () => setState(() => channel = c['channel'] as String),
              ),
            ),
          const SizedBox(height: 8),
          FilledButton(onPressed: busy || channel == null ? null : sendCode, child: Padding(padding: const EdgeInsets.all(12), child: Text(busy ? 'Sending' : 'Send code'))),
          TextButton(onPressed: () => setState(() { step = _Step.matric; error = null; }), child: const Text('Use a different matric number')),
        ]);
      case _Step.code:
        return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          Text('We sent a 6-digit code to $sentTo.${secondsLeft > 0 ? ' It expires in ${mmss(secondsLeft)}.' : ' It has expired. Request a new one.'}'),
          const SizedBox(height: 12),
          TextField(
            controller: codeCtl,
            keyboardType: TextInputType.number,
            maxLength: 6,
            textAlign: TextAlign.center,
            style: const TextStyle(fontSize: 24, letterSpacing: 6),
            decoration: const InputDecoration(border: OutlineInputBorder(), counterText: ''),
            onChanged: (_) => setState(() {}),
            onSubmitted: (_) => codeCtl.text.trim().length == 6 ? verify() : null,
          ),
          const SizedBox(height: 16),
          FilledButton(onPressed: busy || codeCtl.text.trim().length != 6 ? null : verify, child: Padding(padding: const EdgeInsets.all(12), child: Text(busy ? 'Checking' : 'Verify and continue'))),
          Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
            TextButton(onPressed: busy || resendIn > 0 ? null : sendCode, child: Text(resendIn > 0 ? 'Resend in ${resendIn}s' : 'Resend code')),
            TextButton(onPressed: () => setState(() { step = _Step.channel; error = null; }), child: const Text('Change option')),
          ]),
        ]);
    }
  }

  @override
  Widget build(BuildContext context) {
    final status = {'draft': 'Voting has not started', 'open': 'Voting is open', 'closed': 'Voting has closed'}[widget.cfg['election_status']] ?? '';
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(24),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 420),
              child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                if (Api.assetUrl(widget.cfg['logo_url'] as String?) != null)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 12),
                    child: Image.network(Api.assetUrl(widget.cfg['logo_url'] as String?)!, height: 64, alignment: Alignment.centerLeft, errorBuilder: (_, __, ___) => const SizedBox.shrink()),
                  ),
                Text(widget.cfg['institution_name'] as String, style: Theme.of(context).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w600)),
                Text(widget.cfg['election_title'] as String, style: Theme.of(context).textTheme.bodyMedium),
                const SizedBox(height: 32),
                Text('Sign in to vote', style: Theme.of(context).textTheme.headlineSmall),
                const SizedBox(height: 4),
                Text(status, style: Theme.of(context).textTheme.bodySmall),
                const SizedBox(height: 24),
                if (error != null) Padding(padding: const EdgeInsets.only(bottom: 12), child: Text(error!, style: TextStyle(color: Theme.of(context).colorScheme.error))),
                body(context),
                const SizedBox(height: 24),
                Text('Your location, IP address and device are recorded with your vote for election security.', style: Theme.of(context).textTheme.bodySmall, textAlign: TextAlign.center),
              ]),
            ),
          ),
        ),
      ),
    );
  }
}
