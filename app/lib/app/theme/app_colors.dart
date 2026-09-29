import 'package:flutter/material.dart';

/// Moisture scale dry → wet (Design_System.md §2.3).
///
/// Used for fills only (gauges, bars, chart lines); the percentage is always
/// shown next to it as text in `onSurface`.
@immutable
class MoistureColors extends ThemeExtension<MoistureColors> {
  const MoistureColors(this.stops);

  /// Five stops at 0, 25, 50, 75 and 100 %.
  final List<Color> stops;

  static const light = MoistureColors([
    Color(0xFFA06C0A), // Sand
    Color(0xFF5E8A2C), // Leaf
    Color(0xFF1F7F73), // Teal
    Color(0xFF246FA8), // Water
    Color(0xFF243F8F), // Deep water
  ]);

  static const dark = MoistureColors([
    Color(0xFFF0C45C),
    Color(0xFFB5D67A),
    Color(0xFF5CC8B8),
    Color(0xFF6FB4EC),
    Color(0xFFA3B2F7),
  ]);

  static MoistureColors of(BuildContext context) =>
      Theme.of(context).extension<MoistureColors>()!;

  /// Colour for a moisture value in percent, linearly interpolated.
  Color forPercent(num percent) {
    final p = percent.clamp(0, 100).toDouble();
    final segment = (p / 25).floor().clamp(0, stops.length - 2);
    final t = (p - segment * 25) / 25;
    return Color.lerp(stops[segment], stops[segment + 1], t)!;
  }

  @override
  MoistureColors copyWith({List<Color>? stops}) =>
      MoistureColors(stops ?? this.stops);

  @override
  MoistureColors lerp(MoistureColors? other, double t) {
    if (other == null) return this;
    return MoistureColors([
      for (var i = 0; i < stops.length; i++)
        Color.lerp(stops[i], other.stops[i], t)!,
    ]);
  }
}

enum StatusKind { ok, sleeping, pending, warning, error }

/// Status colours (Design_System.md §2.4). Always shown with icon + label.
@immutable
class StatusColors extends ThemeExtension<StatusColors> {
  const StatusColors({
    required this.ok,
    required this.sleeping,
    required this.pending,
    required this.warning,
    required this.error,
    required this.chipAlpha,
  });

  final Color ok;
  final Color sleeping;
  final Color pending;
  final Color warning;
  final Color error;

  /// Opacity of the chip background tint.
  final double chipAlpha;

  static StatusColors light(ColorScheme scheme) => StatusColors(
    ok: const Color(0xFF27692B),
    sleeping: const Color(0xFF505D6B),
    pending: const Color(0xFF0F5AAE),
    warning: const Color(0xFF8A5100),
    error: scheme.error,
    chipAlpha: 0.12,
  );

  static StatusColors dark(ColorScheme scheme) => StatusColors(
    ok: const Color(0xFF81C784),
    sleeping: const Color(0xFFAAB6C2),
    pending: const Color(0xFF9CC3F5),
    warning: const Color(0xFFFFB95C),
    error: scheme.error,
    chipAlpha: 0.16,
  );

  static StatusColors of(BuildContext context) =>
      Theme.of(context).extension<StatusColors>()!;

  Color forKind(StatusKind kind) => switch (kind) {
    StatusKind.ok => ok,
    StatusKind.sleeping => sleeping,
    StatusKind.pending => pending,
    StatusKind.warning => warning,
    StatusKind.error => error,
  };

  @override
  StatusColors copyWith({
    Color? ok,
    Color? sleeping,
    Color? pending,
    Color? warning,
    Color? error,
    double? chipAlpha,
  }) => StatusColors(
    ok: ok ?? this.ok,
    sleeping: sleeping ?? this.sleeping,
    pending: pending ?? this.pending,
    warning: warning ?? this.warning,
    error: error ?? this.error,
    chipAlpha: chipAlpha ?? this.chipAlpha,
  );

  @override
  StatusColors lerp(StatusColors? other, double t) {
    if (other == null) return this;
    return StatusColors(
      ok: Color.lerp(ok, other.ok, t)!,
      sleeping: Color.lerp(sleeping, other.sleeping, t)!,
      pending: Color.lerp(pending, other.pending, t)!,
      warning: Color.lerp(warning, other.warning, t)!,
      error: Color.lerp(error, other.error, t)!,
      chipAlpha: chipAlpha + (other.chipAlpha - chipAlpha) * t,
    );
  }
}
