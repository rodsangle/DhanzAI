import 'package:flutter/material.dart';

IconData fileIcon(String? fileType) => switch (fileType) {
  'pdf' => Icons.picture_as_pdf_outlined,
  'docx' => Icons.description_outlined,
  'xlsx' || 'csv' => Icons.table_chart_outlined,
  'pptx' => Icons.slideshow_outlined,
  'image' => Icons.image_outlined,
  'code' => Icons.code,
  _ => Icons.insert_drive_file_outlined,
};
