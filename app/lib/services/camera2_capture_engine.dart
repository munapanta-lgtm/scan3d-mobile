/// Camera2-only capture engine for Android devices without ARCore.
///
/// Uses real camera for photos but does NOT provide 6DOF pose tracking.
/// poses.json entries will have "pose_4x4": null — COLMAP calculates poses.
library;

import 'package:flutter/services.dart';
import 'capture_engine.dart';

class Camera2OnlyCaptureEngine implements CaptureEngine {
  static const _channel = MethodChannel('com.scan3d.mobile/camera2_engine');
  int? _textureId;

  /// Flutter texture ID for live camera preview, available after startSession.
  int? get previewTextureId => _textureId;

  @override
  Future<void> startSession(String outputDir) async {
    final result = await _channel.invokeMethod<Map>('startSession', {'outputDir': outputDir});
    _textureId = result?['textureId'] as int?;
  }

  @override
  Future<FrameData> captureFrame() async {
    final result = await _channel.invokeMethod<Map>('captureFrame');
    return FrameData.fromMap(result!);
  }

  @override
  Future<void> stopSession() async {
    await _channel.invokeMethod('stopSession');
    _textureId = null;
  }

  @override
  Future<Map<String, dynamic>> getSessionData() async {
    final result = await _channel.invokeMethod<Map>('getSessionData');
    return Map<String, dynamic>.from(result!);
  }
}
