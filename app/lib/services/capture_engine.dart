/// MethodChannel bridge to native ARCore capture engine.
///
/// On Android, this communicates with [CaptureEnginePlugin] via platform
/// channels. On desktop (for UI development), use [MockCaptureEngine].
library;

import 'package:flutter/services.dart';
import 'package:mobile/core/constants.dart';

/// Data returned from a single frame capture.
class FrameData {
  final int frameNumber;
  final double blurScore;
  final List<double>? pose4x4; // 16 elements column-major, null if no ARCore
  final Map<String, double> intrinsics; // fx, fy, cx, cy
  final String imagePath;
  final Uint8List? thumbnail;

  const FrameData({
    required this.frameNumber,
    required this.blurScore,
    required this.intrinsics,
    required this.imagePath,
    this.pose4x4,
    this.thumbnail,
  });

  factory FrameData.fromMap(Map<dynamic, dynamic> map) => FrameData(
        frameNumber: map['frameNumber'] as int,
        blurScore: (map['blurScore'] as num).toDouble(),
        pose4x4: map['pose4x4'] != null
            ? (map['pose4x4'] as List<dynamic>)
                .map((e) => (e as num).toDouble())
                .toList()
            : null,
        intrinsics: Map<String, double>.from(
          (map['intrinsics'] as Map<dynamic, dynamic>).map(
            (k, v) => MapEntry(k.toString(), (v as num).toDouble()),
          ),
        ),
        imagePath: map['imagePath'] as String,
        thumbnail: map['thumbnail'] as Uint8List?,
      );
}

/// Abstract capture engine interface.
abstract class CaptureEngine {
  Future<void> startSession(String outputDir);
  Future<FrameData> captureFrame();
  Future<void> stopSession();
  Future<Map<String, dynamic>> getSessionData();
}

/// Real capture engine using platform MethodChannel (Android only).
class NativeCaptureEngine implements CaptureEngine {
  static const _channel = MethodChannel(kCaptureEngineChannel);

  @override
  Future<void> startSession(String outputDir) async {
    await _channel.invokeMethod('startSession', {'outputDir': outputDir});
  }

  @override
  Future<FrameData> captureFrame() async {
    final result = await _channel.invokeMethod<Map>('captureFrame');
    return FrameData.fromMap(result!);
  }

  @override
  Future<void> stopSession() async {
    await _channel.invokeMethod('stopSession');
  }

  @override
  Future<Map<String, dynamic>> getSessionData() async {
    final result = await _channel.invokeMethod<Map>('getSessionData');
    return Map<String, dynamic>.from(result!);
  }
}
