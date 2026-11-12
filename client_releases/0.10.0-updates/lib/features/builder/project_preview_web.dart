import 'package:flutter/material.dart';
import 'package:web/web.dart' as web;

class ProjectPreview extends StatelessWidget {
  const ProjectPreview({super.key, required this.document, this.height = 420});
  final String document;
  final double height;
  @override
  Widget build(BuildContext context) => SizedBox(
    height: height,
    child: HtmlElementView.fromTagName(
      key: ValueKey(document),
      tagName: 'iframe',
      onElementCreated: (element) {
        final frame = element as web.HTMLIFrameElement;
        frame.setAttribute('sandbox', 'allow-scripts');
        frame.setAttribute('referrerpolicy', 'no-referrer');
        frame.title = 'Generated app preview';
        frame.style.width = '100%';
        frame.style.height = '100%';
        frame.style.border = '0';
        frame.setAttribute('srcdoc', document);
      },
    ),
  );
}
