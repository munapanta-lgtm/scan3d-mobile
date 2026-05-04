package com.scan3d.mobile

import android.Manifest
import android.annotation.SuppressLint
import android.app.Activity
import android.content.pm.PackageManager
import android.graphics.*
import android.hardware.camera2.*
import android.media.ImageReader
import android.os.Handler
import android.os.HandlerThread
import android.util.Size
import android.view.Surface
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodCall
import io.flutter.plugin.common.MethodChannel
import io.flutter.view.TextureRegistry
import java.io.ByteArrayOutputStream
import java.io.File
import java.io.FileOutputStream
import kotlin.math.roundToInt

/**
 * Camera2-only capture engine for devices without ARCore (e.g. Huawei/Honor).
 * Captures real photos but without 6DOF pose tracking.
 * COLMAP will calculate poses from the images.
 */
class Camera2EnginePlugin private constructor(
    private val activity: Activity,
    private val textureRegistry: TextureRegistry
) : MethodChannel.MethodCallHandler {

    companion object {
        private const val CHANNEL = "com.scan3d.mobile/camera2_engine"

        fun registerWith(engine: FlutterEngine, activity: Activity) {
            val channel = MethodChannel(engine.dartExecutor.binaryMessenger, CHANNEL)
            channel.setMethodCallHandler(
                Camera2EnginePlugin(activity, engine.renderer)
            )
        }
    }

    private var cameraDevice: CameraDevice? = null
    private var captureSession: CameraCaptureSession? = null
    private var imageReader: ImageReader? = null
    private var previewSurface: Surface? = null
    private var surfaceTextureEntry: TextureRegistry.SurfaceTextureEntry? = null
    private var bgThread: HandlerThread? = null
    private var bgHandler: Handler? = null
    private var outputDir = ""
    private var frameCount = 0
    private val frameDataList = mutableListOf<Map<String, Any?>>()
    private var camChars: CameraCharacteristics? = null

    override fun onMethodCall(call: MethodCall, result: MethodChannel.Result) {
        when (call.method) {
            "startSession" -> startSession(call, result)
            "captureFrame" -> captureFrame(result)
            "stopSession" -> stopSession(result)
            "getSessionData" -> result.success(mapOf("frameCount" to frameCount, "outputDir" to outputDir))
            else -> result.notImplemented()
        }
    }

    @SuppressLint("MissingPermission")
    private fun startSession(call: MethodCall, result: MethodChannel.Result) {
        outputDir = call.argument<String>("outputDir")!!
        frameCount = 0
        frameDataList.clear()
        File("$outputDir/frames").mkdirs()

        if (ContextCompat.checkSelfPermission(activity, Manifest.permission.CAMERA)
            != PackageManager.PERMISSION_GRANTED
        ) {
            ActivityCompat.requestPermissions(activity, arrayOf(Manifest.permission.CAMERA), 1001)
            result.error("PERMISSION_DENIED", "Camera permission required. Please allow and try again.", null)
            return
        }

        try {
            bgThread = HandlerThread("Camera2BG").also { it.start() }
            bgHandler = Handler(bgThread!!.looper)

            val mgr = activity.getSystemService(CameraManager::class.java)
            val camId = mgr.cameraIdList.firstOrNull { id ->
                mgr.getCameraCharacteristics(id)
                    .get(CameraCharacteristics.LENS_FACING) == CameraCharacteristics.LENS_FACING_BACK
            } ?: throw IllegalStateException("No rear camera")

            camChars = mgr.getCameraCharacteristics(camId)
            val map = camChars!!.get(CameraCharacteristics.SCALER_STREAM_CONFIGURATION_MAP)!!

            // Full-res for capture
            val jpegSize = map.getOutputSizes(ImageFormat.JPEG)
                .maxByOrNull { it.width * it.height } ?: Size(4032, 3024)
            imageReader = ImageReader.newInstance(jpegSize.width, jpegSize.height, ImageFormat.JPEG, 2)

            // Preview texture for Flutter
            val previewSizes = map.getOutputSizes(SurfaceTexture::class.java)
            val prevSize = previewSizes
                .filter { it.width <= 1920 && it.height <= 1080 }
                .maxByOrNull { it.width * it.height }
                ?: previewSizes.minByOrNull { Math.abs(it.width * it.height - 1920 * 1080) }
                ?: Size(1920, 1080)

            surfaceTextureEntry = textureRegistry.createSurfaceTexture()
            val st = surfaceTextureEntry!!.surfaceTexture()
            st.setDefaultBufferSize(prevSize.width, prevSize.height)
            previewSurface = Surface(st)

            mgr.openCamera(camId, object : CameraDevice.StateCallback() {
                override fun onOpened(cam: CameraDevice) {
                    cameraDevice = cam
                    createSession(result)
                }
                override fun onDisconnected(cam: CameraDevice) { cam.close(); cameraDevice = null }
                override fun onError(cam: CameraDevice, err: Int) {
                    cam.close(); cameraDevice = null
                    result.error("CAMERA_ERROR", "Camera error: $err", null)
                }
            }, bgHandler)
        } catch (e: Exception) {
            result.error("SESSION_ERROR", "Camera init failed: ${e.message}", null)
        }
    }

    private fun createSession(result: MethodChannel.Result) {
        val cam = cameraDevice ?: return
        val surfaces = listOfNotNull(previewSurface, imageReader?.surface)

        cam.createCaptureSession(surfaces, object : CameraCaptureSession.StateCallback() {
            override fun onConfigured(session: CameraCaptureSession) {
                captureSession = session
                val req = cam.createCaptureRequest(CameraDevice.TEMPLATE_PREVIEW).apply {
                    previewSurface?.let { addTarget(it) }
                    set(CaptureRequest.CONTROL_AF_MODE, CaptureRequest.CONTROL_AF_MODE_CONTINUOUS_PICTURE)
                }.build()
                session.setRepeatingRequest(req, null, bgHandler)
                result.success(mapOf("textureId" to (surfaceTextureEntry?.id() ?: -1)))
            }
            override fun onConfigureFailed(s: CameraCaptureSession) {
                result.error("SESSION_ERROR", "Camera session config failed", null)
            }
        }, bgHandler)
    }

    private fun captureFrame(result: MethodChannel.Result) {
        val cam = cameraDevice ?: run { result.error("NO_CAMERA", "Camera not open", null); return }
        val session = captureSession ?: run { result.error("NO_SESSION", "No session", null); return }

        frameCount++
        val filename = "image${frameCount.toString().padStart(5, '0')}.jpeg"
        val imagePath = "$outputDir/frames/$filename"

        imageReader?.setOnImageAvailableListener({ reader ->
            val image = reader.acquireLatestImage() ?: return@setOnImageAvailableListener
            try {
                val buf = image.planes[0].buffer
                val bytes = ByteArray(buf.remaining()); buf.get(bytes)
                FileOutputStream(imagePath).use { it.write(bytes) }

                val bmp = BitmapFactory.decodeByteArray(bytes, 0, bytes.size)
                val blur = computeBlurScore(bmp)

                val tw = 120; val th = (bmp.height.toFloat() / bmp.width * tw).roundToInt()
                val thumb = Bitmap.createScaledBitmap(bmp, tw, th, true)
                val ts = ByteArrayOutputStream(); thumb.compress(Bitmap.CompressFormat.JPEG, 70, ts)
                val thumbBytes = ts.toByteArray(); thumb.recycle(); bmp.recycle()

                val frameData = mapOf<String, Any?>(
                    "frameNumber" to frameCount, "blurScore" to blur,
                    "pose4x4" to null, "intrinsics" to getIntrinsics(),
                    "imagePath" to imagePath, "thumbnail" to thumbBytes
                )
                frameDataList.add(frameData)
                activity.runOnUiThread { result.success(frameData) }
            } finally { image.close() }
        }, bgHandler)

        val req = cam.createCaptureRequest(CameraDevice.TEMPLATE_STILL_CAPTURE).apply {
            imageReader?.surface?.let { addTarget(it) }
            set(CaptureRequest.CONTROL_AF_MODE, CaptureRequest.CONTROL_AF_MODE_CONTINUOUS_PICTURE)
            set(CaptureRequest.JPEG_QUALITY, 95.toByte())
        }.build()
        session.capture(req, null, bgHandler)
    }

    private fun getIntrinsics(): Map<String, Double> {
        val c = camChars ?: return mapOf("fx" to 2800.0, "fy" to 2800.0, "cx" to 2016.0, "cy" to 1512.0)
        val fl = c.get(CameraCharacteristics.LENS_INFO_AVAILABLE_FOCAL_LENGTHS)
        val ss = c.get(CameraCharacteristics.SENSOR_INFO_PHYSICAL_SIZE)
        val pa = c.get(CameraCharacteristics.SENSOR_INFO_PIXEL_ARRAY_SIZE)
        if (fl == null || ss == null || pa == null) {
            return mapOf("fx" to 2800.0, "fy" to 2800.0, "cx" to 2016.0, "cy" to 1512.0)
        }
        val fx = (fl[0] * pa.width / ss.width).toDouble()
        val fy = (fl[0] * pa.height / ss.height).toDouble()
        return mapOf("fx" to fx, "fy" to fy, "cx" to pa.width / 2.0, "cy" to pa.height / 2.0)
    }

    private fun stopSession(result: MethodChannel.Result) {
        captureSession?.close(); captureSession = null
        cameraDevice?.close(); cameraDevice = null
        imageReader?.close(); imageReader = null
        previewSurface?.release(); previewSurface = null
        surfaceTextureEntry?.release(); surfaceTextureEntry = null
        bgThread?.quitSafely(); try { bgThread?.join() } catch (_: Exception) {}
        bgThread = null; bgHandler = null
        result.success(null)
    }

    private fun computeBlurScore(bitmap: Bitmap): Double {
        val scale = if (bitmap.width > 500) 500.0 / bitmap.width else 1.0
        val w = (bitmap.width * scale).roundToInt()
        val h = (bitmap.height * scale).roundToInt()
        val small = Bitmap.createScaledBitmap(bitmap, w, h, true)
        val pixels = IntArray(w * h); small.getPixels(pixels, 0, w, 0, 0, w, h); small.recycle()
        val gray = IntArray(w * h)
        for (i in pixels.indices) {
            val p = pixels[i]
            gray[i] = (0.299 * ((p shr 16) and 0xFF) + 0.587 * ((p shr 8) and 0xFF) + 0.114 * (p and 0xFF)).roundToInt()
        }
        var sum = 0.0; var sumSq = 0.0; var count = 0
        for (y in 1 until h - 1) {
            for (x in 1 until w - 1) {
                val lap = gray[(y-1)*w+x] + gray[(y+1)*w+x] + gray[y*w+(x-1)] + gray[y*w+(x+1)] - 4*gray[y*w+x]
                sum += lap; sumSq += lap.toDouble() * lap; count++
            }
        }
        val mean = sum / count; return (sumSq / count) - (mean * mean)
    }
}
