/// Home screen — scan list with share/export actions.
library;

import 'dart:io';
import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:share_plus/share_plus.dart';
import 'package:path/path.dart' as p;
import 'package:mobile/models/scan.dart';
import 'package:mobile/services/storage_service.dart';
import 'package:mobile/features/capture/capture_screen.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  final _storage = StorageService();
  List<Scan> _scans = [];
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _loadScans();
  }

  Future<void> _loadScans() async {
    final scans = await _storage.getAllScans();
    setState(() {
      _scans = scans;
      _loading = false;
    });
  }

  Color _statusColor(ScanStatus status) => switch (status) {
        ScanStatus.captured => Colors.orange,
        ScanStatus.uploading => Colors.blue,
        ScanStatus.processing => Colors.purple,
        ScanStatus.done => Colors.green,
        ScanStatus.failed => Colors.red,
      };

  IconData _statusIcon(ScanStatus status) => switch (status) {
        ScanStatus.captured => Icons.photo_camera,
        ScanStatus.uploading => Icons.cloud_upload,
        ScanStatus.processing => Icons.hourglass_top,
        ScanStatus.done => Icons.check_circle,
        ScanStatus.failed => Icons.error,
      };

  /// Share .zip via system share sheet (email, Drive, Bluetooth, etc.)
  Future<void> _shareScan(Scan scan) async {
    if (scan.zipPath == null || !await File(scan.zipPath!).exists()) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Zip file not found'),
          backgroundColor: Color(0xFFDA3633),
        ),
      );
      return;
    }

    await Share.shareXFiles(
      [XFile(scan.zipPath!)],
      subject: 'SCAN3D: ${scan.title}',
    );
  }

  /// Copy .zip to public Downloads folder
  Future<void> _saveToDownloads(Scan scan) async {
    if (scan.zipPath == null || !await File(scan.zipPath!).exists()) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Zip file not found'),
          backgroundColor: Color(0xFFDA3633),
        ),
      );
      return;
    }

    try {
      // Android public Downloads directory
      final downloadsDir = Directory('/storage/emulated/0/Download');
      if (!await downloadsDir.exists()) {
        await downloadsDir.create(recursive: true);
      }

      final filename = p.basename(scan.zipPath!);
      final destPath = p.join(downloadsDir.path, filename);
      await File(scan.zipPath!).copy(destPath);

      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Saved to Downloads/$filename'),
          backgroundColor: const Color(0xFF238636),
        ),
      );
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Failed to save: $e'),
          backgroundColor: const Color(0xFFDA3633),
        ),
      );
    }
  }

  /// Delete a scan from DB and disk
  Future<void> _deleteScan(Scan scan) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: const Color(0xFF161B22),
        title: const Text('Delete Scan?', style: TextStyle(color: Colors.white)),
        content: const Text('This will permanently delete this scan.',
            style: TextStyle(color: Colors.grey)),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('Cancel'),
          ),
          TextButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Delete', style: TextStyle(color: Colors.red)),
          ),
        ],
      ),
    );
    if (confirmed != true) return;

    // Delete zip file
    if (scan.zipPath != null) {
      try {
        final f = File(scan.zipPath!);
        if (await f.exists()) await f.delete();
      } catch (_) {}
    }
    // Delete scan dir
    try {
      final scanDir = await _storage.getScanDirectory(scan.id);
      final dir = Directory(scanDir);
      if (await dir.exists()) await dir.delete(recursive: true);
    } catch (_) {}

    await _storage.deleteScan(scan.id);
    _loadScans();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF0D1117),
      appBar: AppBar(
        title: const Text(
          'SCAN3D',
          style: TextStyle(fontWeight: FontWeight.w700, letterSpacing: 2),
        ),
        backgroundColor: const Color(0xFF161B22),
        foregroundColor: Colors.white,
        elevation: 0,
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _scans.isEmpty
              ? _buildEmptyState()
              : _buildScanList(),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () async {
          await Navigator.push(
            context,
            MaterialPageRoute(builder: (_) => const CaptureScreen()),
          );
          _loadScans();
        },
        backgroundColor: const Color(0xFF238636),
        icon: const Icon(Icons.add_a_photo, color: Colors.white),
        label: const Text('New Scan',
            style: TextStyle(color: Colors.white, fontWeight: FontWeight.w600)),
      ),
    );
  }

  Widget _buildEmptyState() {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(Icons.view_in_ar, size: 80, color: Colors.grey[700]),
          const SizedBox(height: 16),
          Text('No scans yet',
              style: TextStyle(
                  color: Colors.grey[500],
                  fontSize: 18,
                  fontWeight: FontWeight.w500)),
          const SizedBox(height: 8),
          Text('Tap "New Scan" to capture your first 3D model',
              style: TextStyle(color: Colors.grey[600], fontSize: 14)),
        ],
      ),
    );
  }

  Widget _buildScanList() {
    return ListView.builder(
      padding: const EdgeInsets.all(16),
      itemCount: _scans.length,
      itemBuilder: (context, index) {
        final scan = _scans[index];
        return Card(
          color: const Color(0xFF161B22),
          margin: const EdgeInsets.only(bottom: 12),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
          child: Padding(
            padding: const EdgeInsets.all(12),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // Top row: icon + info + status
                Row(
                  children: [
                    Container(
                      width: 48,
                      height: 48,
                      decoration: BoxDecoration(
                        color: const Color(0xFF21262D),
                        borderRadius: BorderRadius.circular(8),
                      ),
                      child: Icon(Icons.view_in_ar,
                          color: _statusColor(scan.status), size: 24),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(scan.title,
                              style: const TextStyle(
                                  color: Colors.white,
                                  fontWeight: FontWeight.w600,
                                  fontSize: 15)),
                          const SizedBox(height: 2),
                          Text(
                            '${scan.frameCount} frames · ${DateFormat.yMMMd().format(scan.createdAt)}',
                            style: TextStyle(
                                color: Colors.grey[500], fontSize: 12),
                          ),
                        ],
                      ),
                    ),
                    Container(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 8, vertical: 4),
                      decoration: BoxDecoration(
                        color: _statusColor(scan.status).withValues(alpha: 0.15),
                        borderRadius: BorderRadius.circular(8),
                      ),
                      child: Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Icon(_statusIcon(scan.status),
                              color: _statusColor(scan.status), size: 14),
                          const SizedBox(width: 4),
                          Text(scan.status.name.toUpperCase(),
                              style: TextStyle(
                                color: _statusColor(scan.status),
                                fontSize: 10,
                                fontWeight: FontWeight.w700,
                              )),
                        ],
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 10),
                // Action buttons row
                Row(
                  children: [
                    _ActionChip(
                      icon: Icons.share,
                      label: 'Share',
                      color: Colors.blue,
                      onTap: () => _shareScan(scan),
                    ),
                    const SizedBox(width: 8),
                    _ActionChip(
                      icon: Icons.download,
                      label: 'Downloads',
                      color: const Color(0xFF238636),
                      onTap: () => _saveToDownloads(scan),
                    ),
                    const Spacer(),
                    _ActionChip(
                      icon: Icons.delete_outline,
                      label: 'Delete',
                      color: const Color(0xFFDA3633),
                      onTap: () => _deleteScan(scan),
                    ),
                  ],
                ),
              ],
            ),
          ),
        );
      },
    );
  }
}

// ---------------------------------------------------------------------------
// Action chip button
// ---------------------------------------------------------------------------

class _ActionChip extends StatelessWidget {
  final IconData icon;
  final String label;
  final Color color;
  final VoidCallback onTap;

  const _ActionChip({
    required this.icon,
    required this.label,
    required this.color,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(8),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
        decoration: BoxDecoration(
          color: color.withValues(alpha: 0.1),
          borderRadius: BorderRadius.circular(8),
          border: Border.all(color: color.withValues(alpha: 0.3), width: 1),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, color: color, size: 16),
            const SizedBox(width: 6),
            Text(label,
                style: TextStyle(
                    color: color, fontSize: 12, fontWeight: FontWeight.w600)),
          ],
        ),
      ),
    );
  }
}
