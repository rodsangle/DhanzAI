const _resolutionRank = {'384x216': 1, '512x288': 2, '720p': 3, '1080p': 4, '4k': 5};

String? preferredCreativeResolution(Map<String, dynamic> model) {
  final resolutions = (model['resolutions'] as List? ?? []).cast<String>().toList();
  if (resolutions.isEmpty) return null;
  resolutions.sort((a, b) => (_resolutionRank[b] ?? 0).compareTo(_resolutionRank[a] ?? 0));
  return resolutions.first;
}

List<Map<String, dynamic>> creativeModelsByQuality(Iterable<Map<String, dynamic>> models) {
  int resolutionRank(Map<String, dynamic> model) => _resolutionRank[preferredCreativeResolution(model)] ?? 0;
  final sorted = models.toList();
  sorted.sort((a, b) {
    final quality = ((b['quality_rank'] as num?) ?? resolutionRank(b)).compareTo(
      (a['quality_rank'] as num?) ?? resolutionRank(a),
    );
    return quality != 0 ? quality : resolutionRank(b).compareTo(resolutionRank(a));
  });
  return sorted;
}
