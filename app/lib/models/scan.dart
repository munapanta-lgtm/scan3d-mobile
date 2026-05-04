/// Data model for a scan session.
library;

enum ScanStatus { captured, uploading, processing, done, failed }

class Scan {
  final String id;
  final String title;
  final DateTime createdAt;
  final ScanStatus status;
  final int frameCount;
  final String? thumbnailPath;
  final String? zipPath;

  const Scan({
    required this.id,
    required this.title,
    required this.createdAt,
    required this.status,
    this.frameCount = 0,
    this.thumbnailPath,
    this.zipPath,
  });

  Scan copyWith({
    String? title,
    ScanStatus? status,
    int? frameCount,
    String? thumbnailPath,
    String? zipPath,
  }) {
    return Scan(
      id: id,
      title: title ?? this.title,
      createdAt: createdAt,
      status: status ?? this.status,
      frameCount: frameCount ?? this.frameCount,
      thumbnailPath: thumbnailPath ?? this.thumbnailPath,
      zipPath: zipPath ?? this.zipPath,
    );
  }

  Map<String, dynamic> toMap() => {
        'id': id,
        'title': title,
        'created_at': createdAt.toIso8601String(),
        'status': status.name,
        'frame_count': frameCount,
        'thumbnail_path': thumbnailPath,
        'zip_path': zipPath,
      };

  factory Scan.fromMap(Map<String, dynamic> map) => Scan(
        id: map['id'] as String,
        title: map['title'] as String,
        createdAt: DateTime.parse(map['created_at'] as String),
        status: ScanStatus.values.byName(map['status'] as String),
        frameCount: map['frame_count'] as int? ?? 0,
        thumbnailPath: map['thumbnail_path'] as String?,
        zipPath: map['zip_path'] as String?,
      );
}
