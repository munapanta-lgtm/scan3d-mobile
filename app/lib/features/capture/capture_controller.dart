/// State management for the capture session.
library;

import 'package:flutter/foundation.dart';
import 'package:mobile/services/capture_engine.dart';
import 'package:mobile/core/constants.dart';

class CaptureController extends ChangeNotifier {
  final CaptureEngine _engine;

  CaptureController(this._engine);

  // -- State --
  bool _isSessionActive = false;
  bool _isCapturing = false;
  String _outputDir = '';
  final List<FrameData> _frames = [];
  String _guidanceText = 'Tap the button to start capturing';
  double _lastBlurScore = 0;

  // -- Getters --
  bool get isSessionActive => _isSessionActive;
  bool get isCapturing => _isCapturing;
  int get frameCount => _frames.length;
  List<FrameData> get frames => List.unmodifiable(_frames);
  String get guidanceText => _guidanceText;
  double get lastBlurScore => _lastBlurScore;
  String get outputDir => _outputDir;

  int get blurryFrameCount =>
      _frames.where((f) => f.blurScore < kBlurThresholdMarginal).length;

  int get goodFrameCount =>
      _frames.where((f) => f.blurScore >= kBlurThresholdGood).length;

  double get qualityScore {
    if (_frames.isEmpty) return 0;
    return goodFrameCount / _frames.length;
  }

  BlurLevel get blurLevel {
    if (_lastBlurScore >= kBlurThresholdGood) return BlurLevel.good;
    if (_lastBlurScore >= kBlurThresholdMarginal) return BlurLevel.marginal;
    return BlurLevel.blurry;
  }

  // -- Actions --

  Future<void> startSession(String outputDir) async {
    _outputDir = outputDir;
    _frames.clear();
    _isSessionActive = true;
    _guidanceText = 'Move slowly around the object';
    notifyListeners();

    await _engine.startSession(outputDir);
  }

  Future<void> captureFrame() async {
    if (!_isSessionActive || _isCapturing) return;

    _isCapturing = true;
    notifyListeners();

    try {
      final frame = await _engine.captureFrame();
      _frames.add(frame);
      _lastBlurScore = frame.blurScore;

      // Update guidance
      if (frame.blurScore < kBlurThresholdMarginal) {
        _guidanceText = 'Too blurry — hold still';
      } else if (_frames.length < 20) {
        _guidanceText = 'Good! Keep moving slowly around the object';
      } else if (_frames.length < 50) {
        _guidanceText = 'Great coverage! Try different angles';
      } else {
        _guidanceText = 'Excellent! You can stop or capture more';
      }
    } catch (e) {
      _guidanceText = 'Capture failed: $e';
    } finally {
      _isCapturing = false;
      notifyListeners();
    }
  }

  Future<Map<String, dynamic>> stopSession() async {
    _isSessionActive = false;
    notifyListeners();

    await _engine.stopSession();

    // Build poses map for zip
    final poses = <String, dynamic>{};
    for (final frame in _frames) {
      final filename =
          'image${frame.frameNumber.toString().padLeft(5, '0')}.jpeg';
      poses[filename] = {
        'pose_4x4': frame.pose4x4,
        'timestamp': DateTime.now().millisecondsSinceEpoch,
        'intrinsics': frame.intrinsics,
      };
    }

    return poses;
  }

  @override
  void dispose() {
    if (_isSessionActive) {
      _engine.stopSession();
    }
    super.dispose();
  }
}

enum BlurLevel { good, marginal, blurry }
