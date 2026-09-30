import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:mobile_scanner/mobile_scanner.dart';

/// Builds the camera view that reports the text of scanned QR codes. Tests replace it.
typedef LabelScannerBuilder = Widget Function(void Function(String text) onText);

final labelScannerBuilderProvider = Provider<LabelScannerBuilder>(
  (ref) =>
      (onText) => _CameraScanner(onText: onText),
);

class _CameraScanner extends StatefulWidget {
  const _CameraScanner({required this.onText});

  final void Function(String text) onText;

  @override
  State<_CameraScanner> createState() => _CameraScannerState();
}

class _CameraScannerState extends State<_CameraScanner> {
  final _controller = MobileScannerController(formats: const [BarcodeFormat.qrCode]);

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => MobileScanner(
    controller: _controller,
    onDetect: (capture) {
      for (final b in capture.barcodes) {
        final text = b.rawValue;
        if (text != null) widget.onText(text);
      }
    },
    errorBuilder: (context, error) => Center(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Text(
          error.errorDetails?.message ?? error.errorCode.name,
          textAlign: TextAlign.center,
        ),
      ),
    ),
  );
}
