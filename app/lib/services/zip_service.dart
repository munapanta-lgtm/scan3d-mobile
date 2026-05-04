/// Packages captured frames + metadata into a .zip for cv-engine.
///
/// Output structure:
/// ```
/// scan_<uuid>/
/// ├── frames/
/// │   ├── image00001.jpeg
/// │   └── ...
/// ├── poses.json
/// └── metadata.json
/// ```
library;

import 'dart:convert';
import 'dart:io';
import 'package:archive/archive.dart';
import 'package:path/path.dart' as p;

class ZipService {
  /// Package a scan directory into a .zip file.
  ///
  /// [scanDir] must contain a `frames/` subdirectory.
  /// [poses] is the map of {filename: {pose_4x4, timestamp, intrinsics}}.
  /// [metadata] is device/capture metadata.
  /// [outputPath] is the full path for the output .zip file.
  Future<String> packageScan({
    required String scanDir,
    required Map<String, dynamic> poses,
    required Map<String, dynamic> metadata,
    required String outputPath,
  }) async {
    final archive = Archive();
    final scanName = p.basename(scanDir);

    // Add frames
    final framesDir = Directory(p.join(scanDir, 'frames'));
    if (await framesDir.exists()) {
      await for (final entity in framesDir.list()) {
        if (entity is File) {
          final filename = p.basename(entity.path);
          final bytes = await entity.readAsBytes();
          archive.addFile(
            ArchiveFile(
              '$scanName/frames/$filename',
              bytes.length,
              bytes,
            ),
          );
        }
      }
    }

    // Add poses.json
    final posesJson = utf8.encode(
      const JsonEncoder.withIndent('  ').convert(poses),
    );
    archive.addFile(
      ArchiveFile('$scanName/poses.json', posesJson.length, posesJson),
    );

    // Add metadata.json
    final metaJson = utf8.encode(
      const JsonEncoder.withIndent('  ').convert(metadata),
    );
    archive.addFile(
      ArchiveFile('$scanName/metadata.json', metaJson.length, metaJson),
    );

    // Encode and write
    final zipData = ZipEncoder().encode(archive);

    final outputFile = File(outputPath);
    await outputFile.writeAsBytes(zipData);

    return outputPath;
  }
}
