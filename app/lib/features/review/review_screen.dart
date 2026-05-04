/// Review screen — post-capture summary with submit/discard actions.
library;

import 'dart:io';
import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:mobile/core/constants.dart';
import 'package:mobile/models/scan.dart';
import 'package:mobile/services/storage_service.dart';
import 'package:mobile/services/zip_service.dart';
import 'package:mobile/features/capture/capture_controller.dart';

class ReviewScreen extends StatefulWidget {
  final String scanId;
  final CaptureController controller;
  final Map<String, dynamic> poses;

  const ReviewScreen({
    super.key,
    required this.scanId,
    required this.controller,
    required this.poses,
  });

  @override
  State<ReviewScreen> createState() => _ReviewScreenState();
}

class _ReviewScreenState extends State<ReviewScreen> {
  final _storage = StorageService();
  final _zip = ZipService();
  bool _submitting = false;

  CaptureController get ctrl => widget.controller;

  Future<void> _submit() async {
    // Enforce minimum photo count
    if (ctrl.frameCount < kMinFrames) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Need at least $kMinFrames photos to create a scan '
              '(currently ${ctrl.frameCount})'),
          backgroundColor: const Color(0xFFDA3633),
        ),
      );
      return;
    }

    setState(() => _submitting = true);

    try {
      // Build metadata
      final metadata = <String, dynamic>{
        'device_model': 'Unknown (Mock)',
        'android_version': 'N/A',
        'arcore_version': 'N/A',
        'capture_date': DateTime.now().toIso8601String(),
        'frame_count': ctrl.frameCount,
        'quality_score': ctrl.qualityScore,
      };

      // Package zip
      final zipDir = await _storage.getZipDirectory();
      final zipPath = '$zipDir/scan_${widget.scanId}.zip';
      await _zip.packageScan(
        scanDir: ctrl.outputDir,
        poses: widget.poses,
        metadata: metadata,
        outputPath: zipPath,
      );

      // Save to database
      final scan = Scan(
        id: widget.scanId,
        title: 'Scan ${DateFormat.Hm().format(DateTime.now())}',
        createdAt: DateTime.now(),
        status: ScanStatus.captured,
        frameCount: ctrl.frameCount,
        zipPath: zipPath,
      );
      await _storage.insertScan(scan);

      if (!mounted) return;
      // Return to home
      Navigator.of(context).popUntil((route) => route.isFirst);
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Failed to save: $e'),
          backgroundColor: Colors.red,
        ),
      );
    } finally {
      if (mounted) setState(() => _submitting = false);
    }
  }

  Future<void> _discard() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: const Color(0xFF161B22),
        title:
            const Text('Discard Scan?', style: TextStyle(color: Colors.white)),
        content: const Text(
          'This will delete all captured frames.',
          style: TextStyle(color: Colors.grey),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('Cancel'),
          ),
          TextButton(
            onPressed: () => Navigator.pop(ctx, true),
            child:
                const Text('Discard', style: TextStyle(color: Colors.red)),
          ),
        ],
      ),
    );

    if (confirmed == true) {
      // Delete temp files
      try {
        final dir = Directory(ctrl.outputDir);
        if (await dir.exists()) await dir.delete(recursive: true);
      } catch (_) {}

      if (!mounted) return;
      Navigator.of(context).popUntil((route) => route.isFirst);
    }
  }

  @override
  Widget build(BuildContext context) {
    final quality = ctrl.qualityScore;
    final qualityColor = quality >= 0.7
        ? const Color(0xFF238636)
        : quality >= 0.4
            ? const Color(0xFFD29922)
            : const Color(0xFFDA3633);

    return Scaffold(
      backgroundColor: const Color(0xFF0D1117),
      appBar: AppBar(
        title: const Text('Review Capture'),
        backgroundColor: const Color(0xFF161B22),
        foregroundColor: Colors.white,
        elevation: 0,
      ),
      body: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            // Stats cards
            Row(
              children: [
                _StatCard(
                  icon: Icons.photo_library,
                  label: 'Total Frames',
                  value: '${ctrl.frameCount}',
                  color: Colors.blue,
                ),
                const SizedBox(width: 12),
                _StatCard(
                  icon: Icons.blur_on,
                  label: 'Blurry',
                  value: '${ctrl.blurryFrameCount}',
                  color: const Color(0xFFDA3633),
                ),
                const SizedBox(width: 12),
                _StatCard(
                  icon: Icons.check_circle,
                  label: 'Sharp',
                  value: '${ctrl.goodFrameCount}',
                  color: const Color(0xFF238636),
                ),
              ],
            ),
            const SizedBox(height: 20),

            // Quality score
            Container(
              padding: const EdgeInsets.all(20),
              decoration: BoxDecoration(
                color: const Color(0xFF161B22),
                borderRadius: BorderRadius.circular(16),
                border: Border.all(
                    color: qualityColor.withValues(alpha: 0.3), width: 1),
              ),
              child: Column(
                children: [
                  Text(
                    'Quality Score',
                    style: TextStyle(color: Colors.grey[500], fontSize: 14),
                  ),
                  const SizedBox(height: 8),
                  Text(
                    '${(quality * 100).toInt()}%',
                    style: TextStyle(
                      color: qualityColor,
                      fontSize: 48,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                  const SizedBox(height: 8),
                  LinearProgressIndicator(
                    value: quality,
                    backgroundColor: Colors.grey[800],
                    color: qualityColor,
                    minHeight: 6,
                    borderRadius: BorderRadius.circular(3),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 20),

            // Frame grid (scrollable)
            Expanded(
              child: Container(
                decoration: BoxDecoration(
                  color: const Color(0xFF161B22),
                  borderRadius: BorderRadius.circular(16),
                ),
                padding: const EdgeInsets.all(12),
                child: ctrl.frames.isEmpty
                    ? const Center(
                        child: Text('No frames',
                            style: TextStyle(color: Colors.grey)))
                    : GridView.builder(
                        gridDelegate:
                            const SliverGridDelegateWithFixedCrossAxisCount(
                          crossAxisCount: 5,
                          mainAxisSpacing: 6,
                          crossAxisSpacing: 6,
                        ),
                        itemCount: ctrl.frames.length,
                        itemBuilder: (context, index) {
                          final frame = ctrl.frames[index];
                          final isBlurry = frame.blurScore < 100;
                          return Container(
                            decoration: BoxDecoration(
                              color: const Color(0xFF21262D),
                              borderRadius: BorderRadius.circular(6),
                              border: isBlurry
                                  ? Border.all(
                                      color: const Color(0xFFDA3633),
                                      width: 2)
                                  : null,
                            ),
                            child: Center(
                              child: Text(
                                '${frame.frameNumber}',
                                style: TextStyle(
                                  color: isBlurry
                                      ? const Color(0xFFDA3633)
                                      : Colors.grey[500],
                                  fontSize: 11,
                                  fontWeight: FontWeight.w600,
                                ),
                              ),
                            ),
                          );
                        },
                      ),
              ),
            ),
            const SizedBox(height: 20),

            // Action buttons
            Row(
              children: [
                Expanded(
                  child: OutlinedButton.icon(
                    onPressed: _submitting ? null : _discard,
                    style: OutlinedButton.styleFrom(
                      foregroundColor: const Color(0xFFDA3633),
                      side: const BorderSide(color: Color(0xFFDA3633)),
                      padding: const EdgeInsets.symmetric(vertical: 14),
                      shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(12)),
                    ),
                    icon: const Icon(Icons.delete_outline),
                    label: const Text('Discard',
                        style: TextStyle(fontWeight: FontWeight.w600)),
                  ),
                ),
                const SizedBox(width: 16),
                Expanded(
                  flex: 2,
                  child: FilledButton.icon(
                    onPressed: _submitting ? null : _submit,
                    style: FilledButton.styleFrom(
                      backgroundColor: const Color(0xFF238636),
                      foregroundColor: Colors.white,
                      padding: const EdgeInsets.symmetric(vertical: 14),
                      shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(12)),
                    ),
                    icon: _submitting
                        ? const SizedBox(
                            width: 18,
                            height: 18,
                            child: CircularProgressIndicator(
                                strokeWidth: 2, color: Colors.white),
                          )
                        : const Icon(Icons.save_alt),
                    label: Text(
                      _submitting ? 'Saving...' : 'Save & Package',
                      style: const TextStyle(fontWeight: FontWeight.w600),
                    ),
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Stat card widget
// ---------------------------------------------------------------------------

class _StatCard extends StatelessWidget {
  final IconData icon;
  final String label;
  final String value;
  final Color color;

  const _StatCard({
    required this.icon,
    required this.label,
    required this.value,
    required this.color,
  });

  @override
  Widget build(BuildContext context) {
    return Expanded(
      child: Container(
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: const Color(0xFF161B22),
          borderRadius: BorderRadius.circular(12),
        ),
        child: Column(
          children: [
            Icon(icon, color: color, size: 22),
            const SizedBox(height: 6),
            Text(
              value,
              style: TextStyle(
                  color: Colors.white,
                  fontSize: 22,
                  fontWeight: FontWeight.w700),
            ),
            const SizedBox(height: 2),
            Text(
              label,
              style: TextStyle(color: Colors.grey[600], fontSize: 11),
            ),
          ],
        ),
      ),
    );
  }
}
