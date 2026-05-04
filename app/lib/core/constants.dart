/// App-wide constants for SCAN3D MOBILE.
library;

// ---------------------------------------------------------------------------
// Blur detection thresholds (Laplacian variance)
// ---------------------------------------------------------------------------

/// Variance above this = sharp image (green indicator).
const double kBlurThresholdGood = 200.0;

/// Variance between this and [kBlurThresholdGood] = marginal (yellow).
const double kBlurThresholdMarginal = 100.0;

/// Below [kBlurThresholdMarginal] = blurry, discard (red).

// ---------------------------------------------------------------------------
// Capture limits
// ---------------------------------------------------------------------------

const int kMinFrames = 10;
const int kMaxFrames = 200;
const int kRecommendedFrames = 80;

// ---------------------------------------------------------------------------
// File & format
// ---------------------------------------------------------------------------

const Set<String> kValidImageExtensions = {'.jpg', '.jpeg', '.png'};
const String kFramePrefix = 'image';
const String kFrameExtension = '.jpeg';

// ---------------------------------------------------------------------------
// MethodChannel
// ---------------------------------------------------------------------------

const String kCaptureEngineChannel = 'com.scan3d.mobile/capture_engine';
