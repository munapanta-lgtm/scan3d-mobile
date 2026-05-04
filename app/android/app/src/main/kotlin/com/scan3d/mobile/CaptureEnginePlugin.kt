package com.scan3d.mobile

import android.app.Activity
import android.graphics.ImageFormat
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.os.Build
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodCall
import io.flutter.plugin.common.MethodChannel
import com.google.ar.core.*
import java.io.File
import java.io.FileOutputStream
import java.io.ByteArrayOutputStream
import java.nio.ByteBuffer
import kotlin.math.roundToInt

/**
 * Native CaptureEngine for ARCore + Camera integration.
 *
 * Communicates with Flutter via MethodChannel "com.scan3d.mobile/capture_engine".
 *
 * Methods:
 *   startSession(outputDir: String) — Initialize ARCore session and output directory
 *   captureFrame() — Capture current frame, compute blur, extract pose
 *   stopSession() — Release ARCore session
 *   getSessionData() — Return session summary
 */
class CaptureEnginePlugin private constructor(
    private val activity: Activity
) : MethodChannel.MethodCallHandler {

    companion object {
        private const val CHANNEL = "com.scan3d.mobile/capture_engine"

        fun registerWith(engine: FlutterEngine, activity: Activity) {
            val channel = MethodChannel(engine.dartExecutor.binaryMessenger, CHANNEL)
            channel.setMethodCallHandler(CaptureEnginePlugin(activity))
        }
    }

    private var arSession: Session? = null
    private var outputDir: String = ""
    private var frameCount: Int = 0
    private val frameDataList = mutableListOf<Map<String, Any>>()

    override fun onMethodCall(call: MethodCall, result: MethodChannel.Result) {
        when (call.method) {
            "startSession" -> {
                try {
                    outputDir = call.argument<String>("outputDir")!!
                    frameCount = 0
                    frameDataList.clear()

                    // Create frames directory
                    File("$outputDir/frames").mkdirs()

                    // Initialize ARCore
                    arSession = Session(activity).apply {
                        val config = Config(this).apply {
                            updateMode = Config.UpdateMode.LATEST_CAMERA_IMAGE
                            focusMode = Config.FocusMode.AUTO
                        }
                        configure(config)
                        resume()
                    }

                    result.success(null)
                } catch (e: Exception) {
                    result.error("SESSION_ERROR", "Failed to start ARCore session: ${e.message}", null)
                }
            }

            "captureFrame" -> {
                try {
                    val session = arSession ?: throw IllegalStateException("No active session")
                    val frame = session.update()
                    val camera = frame.camera

                    if (camera.trackingState != TrackingState.TRACKING) {
                        result.error("TRACKING_ERROR", "Camera not tracking", null)
                        return
                    }

                    frameCount++

                    // Get camera image
                    val image = frame.acquireCameraImage()
                    val bitmap = imageToBitmap(image)
                    image.close()

                    // Save full-res JPEG
                    val filename = "image${frameCount.toString().padStart(5, '0')}.jpeg"
                    val imagePath = "$outputDir/frames/$filename"
                    FileOutputStream(imagePath).use { fos ->
                        bitmap.compress(Bitmap.CompressFormat.JPEG, 95, fos)
                    }

                    // Compute blur score (Laplacian variance)
                    val blurScore = computeBlurScore(bitmap)

                    // Extract 6DOF pose as 4x4 column-major matrix
                    val pose = camera.displayOrientedPose
                    val poseMatrix = FloatArray(16)
                    pose.toMatrix(poseMatrix, 0)
                    val pose4x4 = poseMatrix.map { it.toDouble() }

                    // Extract camera intrinsics
                    val intrinsics = camera.imageIntrinsics
                    val focalLength = intrinsics.focalLength
                    val principalPoint = intrinsics.principalPoint

                    val intrinsicsMap = mapOf(
                        "fx" to focalLength[0].toDouble(),
                        "fy" to focalLength[1].toDouble(),
                        "cx" to principalPoint[0].toDouble(),
                        "cy" to principalPoint[1].toDouble()
                    )

                    // Generate thumbnail (downscaled)
                    val thumbWidth = 120
                    val thumbHeight = (bitmap.height.toFloat() / bitmap.width * thumbWidth).roundToInt()
                    val thumbnail = Bitmap.createScaledBitmap(bitmap, thumbWidth, thumbHeight, true)
                    val thumbStream = ByteArrayOutputStream()
                    thumbnail.compress(Bitmap.CompressFormat.JPEG, 70, thumbStream)
                    val thumbBytes = thumbStream.toByteArray()
                    thumbnail.recycle()
                    bitmap.recycle()

                    val frameData = mapOf(
                        "frameNumber" to frameCount,
                        "blurScore" to blurScore,
                        "pose4x4" to pose4x4,
                        "intrinsics" to intrinsicsMap,
                        "imagePath" to imagePath,
                        "thumbnail" to thumbBytes
                    )
                    frameDataList.add(frameData)

                    result.success(frameData)
                } catch (e: Exception) {
                    result.error("CAPTURE_ERROR", "Frame capture failed: ${e.message}", null)
                }
            }

            "stopSession" -> {
                arSession?.pause()
                arSession?.close()
                arSession = null
                result.success(null)
            }

            "getSessionData" -> {
                result.success(mapOf(
                    "frameCount" to frameCount,
                    "outputDir" to outputDir
                ))
            }

            else -> result.notImplemented()
        }
    }

    /**
     * Compute Laplacian variance as a blur score.
     * Equivalent to cv2.Laplacian(gray, CV_64F).var()
     * Implemented with a manual 3x3 Laplacian kernel — no OpenCV dependency.
     */
    private fun computeBlurScore(bitmap: Bitmap): Double {
        // Downsample for speed
        val scale = if (bitmap.width > 500) 500.0 / bitmap.width else 1.0
        val w = (bitmap.width * scale).roundToInt()
        val h = (bitmap.height * scale).roundToInt()
        val small = Bitmap.createScaledBitmap(bitmap, w, h, true)

        val pixels = IntArray(w * h)
        small.getPixels(pixels, 0, w, 0, 0, w, h)
        small.recycle()

        // Convert to grayscale
        val gray = IntArray(w * h)
        for (i in pixels.indices) {
            val pixel = pixels[i]
            val r = (pixel shr 16) and 0xFF
            val g = (pixel shr 8) and 0xFF
            val b = pixel and 0xFF
            gray[i] = (0.299 * r + 0.587 * g + 0.114 * b).roundToInt()
        }

        // Apply Laplacian kernel: [0, 1, 0; 1, -4, 1; 0, 1, 0]
        var sum = 0.0
        var sumSq = 0.0
        var count = 0

        for (y in 1 until h - 1) {
            for (x in 1 until w - 1) {
                val lap = gray[(y - 1) * w + x] +
                          gray[(y + 1) * w + x] +
                          gray[y * w + (x - 1)] +
                          gray[y * w + (x + 1)] -
                          4 * gray[y * w + x]
                sum += lap
                sumSq += lap.toDouble() * lap
                count++
            }
        }

        val mean = sum / count
        return (sumSq / count) - (mean * mean) // Variance
    }

    /**
     * Convert ARCore camera Image (YUV_420_888) to Bitmap.
     */
    private fun imageToBitmap(image: android.media.Image): Bitmap {
        val yBuffer = image.planes[0].buffer
        val uBuffer = image.planes[1].buffer
        val vBuffer = image.planes[2].buffer

        val ySize = yBuffer.remaining()
        val uSize = uBuffer.remaining()
        val vSize = vBuffer.remaining()

        val nv21 = ByteArray(ySize + uSize + vSize)
        yBuffer.get(nv21, 0, ySize)
        vBuffer.get(nv21, ySize, vSize)
        uBuffer.get(nv21, ySize + vSize, uSize)

        val yuvImage = android.graphics.YuvImage(
            nv21, ImageFormat.NV21, image.width, image.height, null
        )
        val out = ByteArrayOutputStream()
        yuvImage.compressToJpeg(
            android.graphics.Rect(0, 0, image.width, image.height), 95, out
        )
        val jpegBytes = out.toByteArray()
        return BitmapFactory.decodeByteArray(jpegBytes, 0, jpegBytes.size)
    }
}
