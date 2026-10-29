import 'package:flutter/material.dart';

/// Shown instead of the whole app while the server reports a license problem.
class LicenseScreen extends StatelessWidget {
  final String message;
  final Future<void> Function() onRetry;
  const LicenseScreen({super.key, required this.message, required this.onRetry});

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 420),
              child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                Icon(Icons.lock_outline, size: 56, color: scheme.error),
                const SizedBox(height: 16),
                Text('Application locked', style: Theme.of(context).textTheme.headlineSmall, textAlign: TextAlign.center),
                const SizedBox(height: 12),
                Text(message, textAlign: TextAlign.center),
                const SizedBox(height: 8),
                Text('No election data has been changed or removed.', style: Theme.of(context).textTheme.bodySmall, textAlign: TextAlign.center),
                const SizedBox(height: 24),
                OutlinedButton(onPressed: onRetry, child: const Padding(padding: EdgeInsets.all(12), child: Text('Check again'))),
              ]),
            ),
          ),
        ),
      ),
    );
  }
}
