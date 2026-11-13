import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

Uri? websiteUri(String value) {
  final uri = Uri.tryParse(value);
  if (uri == null ||
      uri.scheme != 'https' ||
      uri.host.isEmpty ||
      uri.userInfo.isNotEmpty ||
      uri.port != 443 ||
      value.contains('\\')) {
    return null;
  }
  return uri;
}

class WebsiteOpenCard extends StatelessWidget {
  const WebsiteOpenCard({super.key, required this.url});
  final String url;

  @override
  Widget build(BuildContext context) {
    final uri = websiteUri(url);
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            SelectableText(url),
            const SizedBox(height: 8),
            FilledButton.icon(
              icon: const Icon(Icons.open_in_new),
              label: const Text('Open website'),
              onPressed: uri == null
                  ? null
                  : () async {
                      var opened = false;
                      try {
                        opened = await launchUrl(
                          uri,
                          mode: LaunchMode.externalApplication,
                          webOnlyWindowName: '_blank',
                        );
                      } catch (_) {}
                      if (!opened && context.mounted) {
                        ScaffoldMessenger.of(context).showSnackBar(
                          const SnackBar(
                            content: Text(
                              'The browser could not open the website. Copy its address above and open it in your browser.',
                            ),
                          ),
                        );
                      }
                    },
            ),
            const Text('Opens on this device. Signing in or interacting with the website remains under your control.'),
          ],
        ),
      ),
    );
  }
}
