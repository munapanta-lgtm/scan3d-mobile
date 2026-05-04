package com.scan3d.mobile

import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine

class MainActivity : FlutterActivity() {
    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        CaptureEnginePlugin.registerWith(flutterEngine, this)
        Camera2EnginePlugin.registerWith(flutterEngine, this)
    }
}
