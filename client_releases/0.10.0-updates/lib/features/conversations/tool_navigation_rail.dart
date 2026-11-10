import 'package:flutter/material.dart';

/// A separate, scrollable tool rail leaves conversation history available.
class ToolNavigationRail extends StatelessWidget {
  const ToolNavigationRail({super.key, required this.onNavigate});

  final ValueChanged<String> onNavigate;

  static const destinations = <({String label, String route, IconData icon})>[
    (label: 'Uploads', route: '/uploads', icon: Icons.cloud_upload_outlined),
    (label: 'Connected operations', route: '/operations', icon: Icons.cloud_sync_outlined),
    (label: 'Chat with Codex', route: '/coding', icon: Icons.terminal),
    (label: 'Media editor', route: '/media-editor', icon: Icons.video_settings),
    (label: 'Voice · Hey Dhanz', route: '/voice', icon: Icons.record_voice_over),
    (label: 'App & agent builder', route: '/builder', icon: Icons.code),
    (label: 'DHANZ Creative Studio', route: '/studio', icon: Icons.auto_awesome_outlined),
    (label: 'Knowledge library', route: '/library', icon: Icons.local_library_outlined),
    (label: 'Integrations', route: '/integrations', icon: Icons.hub_outlined),
    (label: 'Settings', route: '/settings', icon: Icons.settings_outlined),
  ];

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: 64,
      child: Material(
        color: Theme.of(context).colorScheme.surfaceContainer,
        child: ListView(
          padding: const EdgeInsets.symmetric(vertical: 12, horizontal: 8),
          children: [
            for (final destination in destinations)
              Padding(
                padding: const EdgeInsets.only(bottom: 4),
                child: IconButton(
                  tooltip: destination.label,
                  constraints: const BoxConstraints(minWidth: 48, minHeight: 48),
                  onPressed: () => onNavigate(destination.route),
                  icon: Icon(destination.icon),
                ),
              ),
          ],
        ),
      ),
    );
  }
}
