import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api/api_client.dart';
import '../../core/providers.dart';
import '../auth/auth_controller.dart';

typedef FeedbackKey = ({String user, String server, String message});
final responseRatingProvider = FutureProvider.autoDispose
    .family<String?, FeedbackKey>((ref, key) async {
      final result = await ref
          .watch(apiClientProvider)
          .responseFeedback(key.message);
      return result['rating'] as String?;
    });

class ResponseRating extends ConsumerStatefulWidget {
  const ResponseRating({super.key, required this.messageId});
  final String messageId;
  @override
  ConsumerState<ResponseRating> createState() => _ResponseRatingState();
}

class _ResponseRatingState extends ConsumerState<ResponseRating> {
  bool _saving = false;
  Future<void> _save(FeedbackKey key, String? value) async {
    setState(() => _saving = true);
    try {
      await ref.read(apiClientProvider).rateResponse(key.message, value);
      if (!mounted || ref.read(authControllerProvider).value?.id != key.user)
        return;
      await ref.refresh(responseRatingProvider(key).future);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Feedback saved to your account')),
      );
    } on ApiException catch (error) {
      if (mounted)
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text(error.message)));
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final user = ref.watch(authControllerProvider).value;
    if (user == null) return const SizedBox.shrink();
    final key = (
      user: user.id,
      server: ref.watch(apiClientProvider).baseUrl,
      message: widget.messageId,
    );
    final rating = ref.watch(responseRatingProvider(key));
    final enabled = !_saving && rating.hasValue;
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        for (final value in ['up', 'down'])
          IconButton(
            tooltip: rating.hasError
                ? 'Feedback is unavailable on this server'
                : value == 'up'
                ? 'Good response'
                : 'Poor response',
            icon: Icon(
              value == 'up'
                  ? (rating.value == value
                        ? Icons.thumb_up
                        : Icons.thumb_up_outlined)
                  : (rating.value == value
                        ? Icons.thumb_down
                        : Icons.thumb_down_outlined),
            ),
            iconSize: 18,
            visualDensity: VisualDensity.compact,
            color: rating.value == value
                ? Theme.of(context).colorScheme.primary
                : null,
            onPressed: enabled
                ? () => _save(key, rating.value == value ? null : value)
                : null,
          ),
      ],
    );
  }
}
