/// Capture screen — camera preview with overlay controls.
library;

import 'dart:io' show Platform;
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:uuid/uuid.dart';
import 'package:mobile/core/constants.dart';
import 'package:mobile/services/capture_engine.dart';
import 'package:mobile/services/camera2_capture_engine.dart';
import 'package:mobile/services/mock_capture_engine.dart';
import 'package:mobile/services/storage_service.dart';
import 'package:mobile/features/capture/capture_controller.dart';
import 'package:mobile/features/review/review_screen.dart';

class CaptureScreen extends StatefulWidget {
  const CaptureScreen({super.key});

  @override
  State<CaptureScreen> createState() => _CaptureScreenState();
}

enum EngineMode { arcore, camera2, mock }

class _CaptureScreenState extends State<CaptureScreen> {
  CaptureController? _controller;
  final _storage = StorageService();
  late final String _scanId;
  bool _initialized = false;
  bool _cameraReady = false;
  EngineMode _engineMode = EngineMode.mock;
  int? _previewTextureId;

  @override
  void initState() {
    super.initState();
    _scanId = const Uuid().v4();
    _initSession();
  }

  Future<void> _initSession() async {
    final scanDir = await _storage.getScanDirectory(_scanId);

    if (!Platform.isAndroid) {
      // Desktop: mock engine
      _engineMode = EngineMode.mock;
      _controller = CaptureController(MockCaptureEngine());
      await _controller!.startSession(scanDir);
      setState(() { _initialized = true; _cameraReady = true; });
      return;
    }

    // Android: try ARCore first, fallback to Camera2-only
    try {
      final engine = NativeCaptureEngine();
      _controller = CaptureController(engine);
      await _controller!.startSession(scanDir);
      _engineMode = EngineMode.arcore;
      setState(() { _initialized = true; _cameraReady = true; });
    } catch (e) {
      debugPrint('[capture] ARCore unavailable: $e — using Camera2');
      try {
        final engine = Camera2OnlyCaptureEngine();
        _controller = CaptureController(engine);
        await _controller!.startSession(scanDir);
        _previewTextureId = engine.previewTextureId;
        _engineMode = EngineMode.camera2;
        setState(() { _initialized = true; _cameraReady = true; });
      } catch (e2) {
        debugPrint('[capture] Camera2 also failed: $e2');
        if (!mounted) return;
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Camera init failed: $e2'),
            backgroundColor: const Color(0xFFDA3633),
          ),
        );
        Navigator.pop(context);
      }
    }
  }

  @override
  void dispose() {
    _controller?.dispose();
    super.dispose();
  }

  void _onStopPressed() async {
    final poses = await _controller!.stopSession();
    if (!mounted) return;

    Navigator.pushReplacement(
      context,
      MaterialPageRoute(
        builder: (_) => ReviewScreen(
          scanId: _scanId,
          controller: _controller!,
          poses: poses,
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    if (!_initialized || _controller == null) {
      return const Scaffold(
        backgroundColor: Colors.black,
        body: Center(
          child: CircularProgressIndicator(color: Color(0xFF238636)),
        ),
      );
    }

    return ChangeNotifierProvider.value(
      value: _controller!,
      child: Scaffold(
        backgroundColor: Colors.black,
        body: SafeArea(child: _buildCaptureUI()),
      ),
    );
  }

  Widget _buildCaptureUI() {
    return Consumer<CaptureController>(
      builder: (context, ctrl, _) {
        return Stack(
          children: [
            // Camera preview
            Positioned.fill(child: _buildPreview()),

            // Engine mode badge
            if (_engineMode != EngineMode.arcore)
              Positioned(
                top: 50,
                left: 0,
                right: 0,
                child: Center(
                  child: Container(
                    padding:
                        const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                    decoration: BoxDecoration(
                      color: _engineMode == EngineMode.camera2
                          ? const Color(0xFFD29922).withValues(alpha: 0.8)
                          : Colors.black54,
                      borderRadius: BorderRadius.circular(16),
                    ),
                    child: Text(
                      _engineMode == EngineMode.camera2
                          ? '📷 Camera2 · No pose tracking'
                          : '🖥️ Desktop Mock',
                      style:
                          const TextStyle(color: Colors.white, fontSize: 12),
                    ),
                  ),
                ),
              ),

            // Top bar: frame counter + blur indicator
            Positioned(
              top: 0,
              left: 0,
              right: 0,
              child: Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
                decoration: BoxDecoration(
                  gradient: LinearGradient(
                    begin: Alignment.topCenter,
                    end: Alignment.bottomCenter,
                    colors: [
                      Colors.black.withValues(alpha: 0.7),
                      Colors.transparent,
                    ],
                  ),
                ),
                child: Row(
                  children: [
                    Container(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 14, vertical: 8),
                      decoration: BoxDecoration(
                        color: Colors.black54,
                        borderRadius: BorderRadius.circular(20),
                      ),
                      child: Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          const Icon(Icons.photo_library,
                              color: Colors.white70, size: 18),
                          const SizedBox(width: 8),
                          Text(
                            '${ctrl.frameCount} / $kRecommendedFrames',
                            style: const TextStyle(
                              color: Colors.white,
                              fontWeight: FontWeight.w600,
                              fontSize: 16,
                            ),
                          ),
                        ],
                      ),
                    ),
                    const Spacer(),
                    _BlurIndicator(level: ctrl.blurLevel),
                  ],
                ),
              ),
            ),

            // Guidance text
            Positioned(
              bottom: 140,
              left: 20,
              right: 20,
              child: Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
                decoration: BoxDecoration(
                  color: Colors.black54,
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Text(
                  ctrl.guidanceText,
                  textAlign: TextAlign.center,
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 15,
                    fontWeight: FontWeight.w500,
                  ),
                ),
              ),
            ),

            // Bottom controls
            Positioned(
              bottom: 30,
              left: 0,
              right: 0,
              child: Row(
                mainAxisAlignment: MainAxisAlignment.spaceEvenly,
                children: [
                  _ControlButton(
                    icon: Icons.stop,
                    label: 'Stop',
                    color: const Color(0xFFDA3633),
                    onPressed: ctrl.frameCount >= 1 ? _onStopPressed : null,
                  ),
                  GestureDetector(
                    onTap: (!_cameraReady || ctrl.isCapturing)
                        ? null
                        : ctrl.captureFrame,
                    child: AnimatedContainer(
                      duration: const Duration(milliseconds: 150),
                      width: 76,
                      height: 76,
                      decoration: BoxDecoration(
                        shape: BoxShape.circle,
                        color: ctrl.isCapturing
                            ? Colors.grey[700]
                            : const Color(0xFF238636),
                        border: Border.all(color: Colors.white, width: 4),
                        boxShadow: [
                          BoxShadow(
                            color: const Color(0xFF238636)
                                .withValues(alpha: 0.4),
                            blurRadius: 16,
                            spreadRadius: 2,
                          ),
                        ],
                      ),
                      child: ctrl.isCapturing
                          ? const Padding(
                              padding: EdgeInsets.all(20),
                              child: CircularProgressIndicator(
                                  strokeWidth: 3, color: Colors.white),
                            )
                          : const Icon(Icons.camera,
                              color: Colors.white, size: 32),
                    ),
                  ),
                  const SizedBox(width: 64),
                ],
              ),
            ),
          ],
        );
      },
    );
  }

  Widget _buildPreview() {
    // Live camera preview from Camera2 or ARCore
    if (_previewTextureId != null) {
      return Texture(textureId: _previewTextureId!);
    }
    // Mock/fallback: gradient placeholder
    return Container(
      decoration: const BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: [Color(0xFF1A1A2E), Color(0xFF0F0F1A)],
        ),
      ),
      child: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.videocam_off, size: 60, color: Colors.grey[800]),
            const SizedBox(height: 8),
            Text(
              _engineMode == EngineMode.mock
                  ? 'Desktop Mock Mode'
                  : 'Camera Preview',
              style: TextStyle(color: Colors.grey[700], fontSize: 14),
            ),
          ],
        ),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Blur indicator
// ---------------------------------------------------------------------------

class _BlurIndicator extends StatelessWidget {
  final BlurLevel level;
  const _BlurIndicator({required this.level});

  @override
  Widget build(BuildContext context) {
    final (color, label) = switch (level) {
      BlurLevel.good => (const Color(0xFF238636), 'SHARP'),
      BlurLevel.marginal => (const Color(0xFFD29922), 'OK'),
      BlurLevel.blurry => (const Color(0xFFDA3633), 'BLURRY'),
    };
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.25),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: color, width: 1.5),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            width: 10, height: 10,
            decoration: BoxDecoration(shape: BoxShape.circle, color: color),
          ),
          const SizedBox(width: 8),
          Text(label,
              style: TextStyle(
                  color: color, fontWeight: FontWeight.w700, fontSize: 13)),
        ],
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Control button
// ---------------------------------------------------------------------------

class _ControlButton extends StatelessWidget {
  final IconData icon;
  final String label;
  final Color color;
  final VoidCallback? onPressed;

  const _ControlButton({
    required this.icon,
    required this.label,
    required this.color,
    this.onPressed,
  });

  @override
  Widget build(BuildContext context) {
    final isDisabled = onPressed == null;
    return GestureDetector(
      onTap: onPressed,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            width: 52, height: 52,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: isDisabled ? Colors.grey[800] : color.withValues(alpha: 0.2),
              border: Border.all(
                  color: isDisabled ? Colors.grey[700]! : color, width: 2),
            ),
            child: Icon(icon,
                color: isDisabled ? Colors.grey[600] : color, size: 24),
          ),
          const SizedBox(height: 6),
          Text(label,
              style: TextStyle(
                color: isDisabled ? Colors.grey[600] : Colors.white70,
                fontSize: 12, fontWeight: FontWeight.w500)),
        ],
      ),
    );
  }
}
