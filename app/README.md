# SCAN3D MOBILE - Frontend

## Overview
Flutter 3.x mobile application that converts a smartphone into a metric 3D scanner.

## Tech Stack
- **Framework**: Flutter 3.x
- **Native Modules**: Kotlin (ARCore capture, OpenCV validation)
- **Monetization**: Google Play Billing Library
- **Upload Resilience**: WorkManager
- **3D Viewer**: model_viewer_plus / flutter_gl

## Architecture
The app enforces an edge-first quality control approach. It captures ARCore telemetry (poses) alongside visual frames. Before uploading, frames are validated using OpenCV for blur, exposure, and feature density to ensure high-quality reconstruction.

## Development
(Instructions to be added for running the Flutter app and Kotlin native modules locally)
