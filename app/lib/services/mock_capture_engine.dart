/// Mock capture engine for desktop/emulator UI development.
///
/// Simulates ARCore frame capture with deterministic dummy data so the
/// full UI flow (Home → Capture → Review → .zip) can be tested without
/// a physical Android device.
library;

import 'dart:math';
import 'dart:typed_data';
import 'dart:io';

import 'capture_engine.dart';

class MockCaptureEngine implements CaptureEngine {
  final _random = Random(42);
  int _frameCount = 0;
  String _outputDir = '';
  final List<Map<String, dynamic>> _frames = [];

  @override
  Future<void> startSession(String outputDir) async {
    _outputDir = outputDir;
    _frameCount = 0;
    _frames.clear();
    // Create frames directory
    await Directory('$outputDir/frames').create(recursive: true);
  }

  @override
  Future<FrameData> captureFrame() async {
    await Future<void>.delayed(const Duration(milliseconds: 300));
    _frameCount++;

    final filename =
        'image${_frameCount.toString().padLeft(5, '0')}.jpeg';
    final imagePath = '$_outputDir/frames/$filename';

    // Generate a small dummy JPEG-like file (just bytes, not a real image)
    final dummyBytes = Uint8List(1024);
    for (var i = 0; i < dummyBytes.length; i++) {
      dummyBytes[i] = _random.nextInt(256);
    }
    await File(imagePath).writeAsBytes(dummyBytes);

    // Simulate a blur score — mostly sharp, occasionally blurry
    final blurScore = 150.0 + _random.nextDouble() * 200.0;

    // Simulate a 4x4 identity-ish pose with slight rotation
    final angle = _frameCount * 0.05;
    final pose4x4 = <double>[
      cos(angle), -sin(angle), 0, 0, //
      sin(angle), cos(angle), 0, 0, //
      0, 0, 1, 0, //
      _frameCount * 0.01, 0, 0.5, 1, //
    ];

    final intrinsics = <String, double>{
      'fx': 2800.0,
      'fy': 2800.0,
      'cx': 2016.0,
      'cy': 1512.0,
    };

    _frames.add({
      'filename': filename,
      'pose4x4': pose4x4,
      'timestamp': DateTime.now().millisecondsSinceEpoch,
      'intrinsics': intrinsics,
      'blurScore': blurScore,
    });

    return FrameData(
      frameNumber: _frameCount,
      blurScore: blurScore,
      pose4x4: pose4x4,
      intrinsics: intrinsics,
      imagePath: imagePath,
      thumbnail: dummyBytes,
    );
  }

  @override
  Future<void> stopSession() async {
    // Nothing to clean up in mock
  }

  @override
  Future<Map<String, dynamic>> getSessionData() async {
    return {
      'frameCount': _frameCount,
      'frames': _frames,
      'outputDir': _outputDir,
    };
  }
}
