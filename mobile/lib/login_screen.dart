import 'package:flutter/material.dart';
import 'api.dart';

class LoginScreen extends StatefulWidget {
  final Map<String, dynamic> cfg;
  final Future<void> Function() onSignedIn;
  const LoginScreen({super.key, required this.cfg, required this.onSignedIn});
  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final matric = TextEditingController();
  final pin = TextEditingController();
  String? error;
  bool busy = false;

  Future<void> submit() async {
    setState(() { busy = true; error = null; });
    try {
      await Api.login(matric.text.trim(), pin.text);
      await widget.onSignedIn();
    } on ApiException catch (e) {
      setState(() => error = e.message);
    } finally {
      if (mounted) setState(() => busy = false);
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
                Text(widget.cfg['institution_name'] as String, style: Theme.of(context).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w600)),
                Text(widget.cfg['election_title'] as String, style: Theme.of(context).textTheme.bodyMedium),
                const SizedBox(height: 32),
                Text('Sign in to vote', style: Theme.of(context).textTheme.headlineSmall),
                const SizedBox(height: 4),
                Text(status, style: Theme.of(context).textTheme.bodySmall),
                const SizedBox(height: 24),
                if (error != null) Padding(padding: const EdgeInsets.only(bottom: 12), child: Text(error!, style: TextStyle(color: Theme.of(context).colorScheme.error))),
                TextField(controller: matric, decoration: const InputDecoration(labelText: 'Matric number', border: OutlineInputBorder()), textInputAction: TextInputAction.next),
                const SizedBox(height: 16),
                TextField(controller: pin, obscureText: true, keyboardType: TextInputType.number, decoration: const InputDecoration(labelText: 'Voting PIN', border: OutlineInputBorder()), onSubmitted: (_) => submit()),
                const SizedBox(height: 24),
                FilledButton(onPressed: busy ? null : submit, child: Padding(padding: const EdgeInsets.all(12), child: Text(busy ? 'Signing in' : 'Sign in'))),
              ]),
            ),
          ),
        ),
      ),
    );
  }
}
