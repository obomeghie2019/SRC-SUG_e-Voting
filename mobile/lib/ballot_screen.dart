import 'package:flutter/material.dart';
import 'api.dart';

class BallotScreen extends StatefulWidget {
  final Map<String, dynamic> cfg;
  final VoidCallback onSignedOut;
  final Future<void> Function() onRefreshConfig;
  const BallotScreen({super.key, required this.cfg, required this.onSignedOut, required this.onRefreshConfig});
  @override
  State<BallotScreen> createState() => _BallotScreenState();
}

class _BallotScreenState extends State<BallotScreen> {
  Map<String, dynamic>? ballot;
  final Map<int, int> selected = {};
  String? error;
  String? receipt;
  bool submitting = false;

  @override
  void initState() {
    super.initState();
    load();
  }

  Future<void> load() async {
    try {
      await widget.onRefreshConfig();
      final b = await Api.ballot();
      if (mounted) setState(() => ballot = b);
    } on ApiException catch (e) {
      if (e.status == 401) { widget.onSignedOut(); return; }
      if (mounted) setState(() => error = e.message);
    }
  }

  Future<void> signOut() async {
    await Api.logout();
    widget.onSignedOut();
  }

  List<dynamic> get positions => ballot!['positions'] as List<dynamic>;

  Future<void> review() async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Confirm your vote'),
        content: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
          for (final p in positions)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 4),
              child: Text.rich(TextSpan(children: [
                TextSpan(text: '${p['title']}: '),
                TextSpan(
                  text: (p['candidates'] as List).cast<Map<String, dynamic>>().where((c) => c['id'] == selected[p['id']]).map((c) => c['full_name']).firstOrNull ?? 'No selection',
                  style: const TextStyle(fontWeight: FontWeight.w600),
                ),
              ])),
            ),
          const SizedBox(height: 8),
          const Text('You cannot change your vote after submitting.', style: TextStyle(fontSize: 12)),
        ]),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Go back')),
          FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Submit vote')),
        ],
      ),
    );
    if (ok != true) return;
    setState(() { submitting = true; error = null; });
    try {
      final code = await Api.vote(selected);
      setState(() => receipt = code);
    } on ApiException catch (e) {
      setState(() => error = e.message);
    } finally {
      if (mounted) setState(() => submitting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final status = widget.cfg['election_status'] as String;
    return Scaffold(
      appBar: AppBar(
        title: Text(widget.cfg['institution_name'] as String),
        actions: [TextButton(onPressed: signOut, child: const Text('Sign out'))],
      ),
      body: _body(status),
    );
  }

  Widget _centered(String title, [String? sub]) => Center(
        child: Padding(
          padding: const EdgeInsets.all(32),
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            Text(title, textAlign: TextAlign.center, style: Theme.of(context).textTheme.headlineSmall),
            if (sub != null) ...[const SizedBox(height: 12), Text(sub, textAlign: TextAlign.center)],
          ]),
        ),
      );

  Widget _body(String status) {
    if (ballot == null) return error != null ? _centered(error!) : const Center(child: CircularProgressIndicator());
    if (receipt != null) {
      return _centered('Your vote has been recorded', 'Keep this receipt code. It proves your ballot was counted without revealing your choices.\n\n$receipt');
    }
    if (ballot!['has_voted'] == true) return _centered('Your vote has been recorded', 'You have already voted in this election.');
    if (status != 'open') return _centered(status == 'closed' ? 'Voting has closed' : 'Voting has not started yet');

    return Column(children: [
      if (error != null) Container(width: double.infinity, color: Theme.of(context).colorScheme.errorContainer, padding: const EdgeInsets.all(12), child: Text(error!)),
      Expanded(
        child: RefreshIndicator(
          onRefresh: load,
          child: ListView(padding: const EdgeInsets.all(16), children: [
            for (final p in positions) ...[
              Padding(padding: const EdgeInsets.only(top: 8, bottom: 8), child: Text(p['title'] as String, style: Theme.of(context).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w600))),
              RadioGroup<int>(
                groupValue: selected[p['id'] as int],
                onChanged: (v) => setState(() => selected[p['id'] as int] = v!),
                child: Column(children: [
                  for (final c in (p['candidates'] as List).cast<Map<String, dynamic>>())
                    Card(
                      margin: const EdgeInsets.only(bottom: 8),
                      child: RadioListTile<int>(
                        value: c['id'] as int,
                        title: Text(c['full_name'] as String),
                        subtitle: Text([c['department'], c['level']].where((e) => (e as String).isNotEmpty).join(', ') + ((c['manifesto'] as String).isNotEmpty ? '\n${c['manifesto']}' : '')),
                      ),
                    ),
                ]),
              ),
            ],
          ]),
        ),
      ),
      SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: SizedBox(
            width: double.infinity,
            child: FilledButton(
              onPressed: selected.isEmpty || submitting ? null : review,
              child: Padding(padding: const EdgeInsets.all(12), child: Text('Review your choices (${selected.length} of ${positions.length})')),
            ),
          ),
        ),
      ),
    ]);
  }
}
