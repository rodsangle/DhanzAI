import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../core/theme.dart';

/// The DHANZ AI mark: a gold "D" orbit around a navy core with a spark of light.
class DhanzLogo extends StatelessWidget {
  const DhanzLogo({super.key, this.size = 64});

  final double size;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      label: 'DHANZ AI logo',
      image: true,
      child: SizedBox.square(
        dimension: size,
        child: CustomPaint(painter: _LogoPainter()),
      ),
    );
  }
}

class _LogoPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final s = size.width;
    final center = Offset(s / 2, s / 2);
    final rect = Offset.zero & size;

    // Rounded navy tile.
    final tile = RRect.fromRectAndRadius(rect, Radius.circular(s * 0.24));
    canvas.drawRRect(
      tile,
      Paint()
        ..shader = const LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [DhanzColors.navyLight, DhanzColors.navy, DhanzColors.black],
        ).createShader(rect),
    );

    final gold = Paint()
      ..shader = const LinearGradient(
        begin: Alignment.topLeft,
        end: Alignment.bottomRight,
        colors: [DhanzColors.goldLight, DhanzColors.gold, Color(0xFFA9831F)],
      ).createShader(rect)
      ..style = PaintingStyle.stroke
      ..strokeCap = StrokeCap.round
      ..strokeWidth = s * 0.085;

    // The "D": a vertical stem plus a 300° arc.
    final stemX = s * 0.33;
    canvas.drawLine(Offset(stemX, s * 0.27), Offset(stemX, s * 0.73), gold);
    final arcRect = Rect.fromCenter(center: Offset(s * 0.45, s / 2), width: s * 0.46, height: s * 0.46);
    canvas.drawArc(arcRect, -math.pi / 2, math.pi, false, gold);
    canvas.drawLine(Offset(stemX, s * 0.27), Offset(s * 0.45, s * 0.27), gold);
    canvas.drawLine(Offset(stemX, s * 0.73), Offset(s * 0.45, s * 0.73), gold);

    // Spark (the "AI" light).
    final sparkCenter = Offset(s * 0.74, s * 0.26);
    final spark = Path();
    final r = s * 0.09;
    for (var i = 0; i < 8; i++) {
      final angle = i * math.pi / 4;
      final radius = i.isEven ? r : r * 0.32;
      final p = sparkCenter + Offset(math.cos(angle) * radius, math.sin(angle) * radius);
      i == 0 ? spark.moveTo(p.dx, p.dy) : spark.lineTo(p.dx, p.dy);
    }
    spark.close();
    canvas.drawPath(spark, Paint()..color = DhanzColors.goldLight);

    // Subtle inner ring.
    canvas.drawCircle(
      center,
      s * 0.42,
      Paint()
        ..style = PaintingStyle.stroke
        ..strokeWidth = s * 0.012
        ..color = DhanzColors.gold.withValues(alpha: 0.25),
    );
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}

/// Logo plus the app name and tagline, for splash and auth screens.
class DhanzBrandHeader extends StatelessWidget {
  const DhanzBrandHeader({super.key, this.logoSize = 88});

  final double logoSize;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        DhanzLogo(size: logoSize),
        const SizedBox(height: 18),
        Text(
          'DHANZ AI',
          style: theme.textTheme.headlineMedium?.copyWith(fontWeight: FontWeight.w800, letterSpacing: 3),
        ),
        const SizedBox(height: 6),
        Text(
          'Your World. Your Knowledge. Your AI.',
          style: theme.textTheme.bodyMedium?.copyWith(color: theme.colorScheme.secondary, letterSpacing: 0.4),
          textAlign: TextAlign.center,
        ),
      ],
    );
  }
}
