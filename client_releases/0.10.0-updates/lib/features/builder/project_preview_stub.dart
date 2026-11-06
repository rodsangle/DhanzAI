import 'package:flutter/material.dart';

class ProjectPreview extends StatelessWidget {
  const ProjectPreview({super.key, required this.document, this.height = 420});
  final String document;
  final double height;
  @override
  Widget build(BuildContext context) => const Text('Open the web app to preview HTML, or download the project.');
}
