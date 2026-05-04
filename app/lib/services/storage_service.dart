/// Local storage service using SQLite for scan history
/// and file system for frames/zips.
library;

import 'package:path_provider/path_provider.dart';
import 'package:sqflite/sqflite.dart';
import 'package:path/path.dart' as p;
import 'dart:io';
import '../models/scan.dart';

class StorageService {
  Database? _db;

  Future<Database> get database async {
    _db ??= await _initDb();
    return _db!;
  }

  Future<Database> _initDb() async {
    final dbPath = await getDatabasesPath();
    final path = p.join(dbPath, 'scan3d.db');
    return openDatabase(
      path,
      version: 1,
      onCreate: (db, version) async {
        await db.execute('''
          CREATE TABLE scans (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            created_at TEXT NOT NULL,
            status TEXT NOT NULL,
            frame_count INTEGER DEFAULT 0,
            thumbnail_path TEXT,
            zip_path TEXT
          )
        ''');
      },
    );
  }

  // -- CRUD --

  Future<void> insertScan(Scan scan) async {
    final db = await database;
    await db.insert('scans', scan.toMap(),
        conflictAlgorithm: ConflictAlgorithm.replace);
  }

  Future<void> updateScan(Scan scan) async {
    final db = await database;
    await db.update('scans', scan.toMap(),
        where: 'id = ?', whereArgs: [scan.id]);
  }

  Future<void> deleteScan(String id) async {
    final db = await database;
    await db.delete('scans', where: 'id = ?', whereArgs: [id]);
  }

  Future<List<Scan>> getAllScans() async {
    final db = await database;
    final maps = await db.query('scans', orderBy: 'created_at DESC');
    return maps.map(Scan.fromMap).toList();
  }

  Future<Scan?> getScan(String id) async {
    final db = await database;
    final maps = await db.query('scans', where: 'id = ?', whereArgs: [id]);
    if (maps.isEmpty) return null;
    return Scan.fromMap(maps.first);
  }

  // -- File paths --

  Future<String> getScanDirectory(String scanId) async {
    final appDir = await getApplicationDocumentsDirectory();
    final scanDir = Directory(p.join(appDir.path, 'scans', scanId));
    if (!await scanDir.exists()) {
      await scanDir.create(recursive: true);
    }
    return scanDir.path;
  }

  Future<String> getZipDirectory() async {
    final appDir = await getApplicationDocumentsDirectory();
    final zipDir = Directory(p.join(appDir.path, 'zips'));
    if (!await zipDir.exists()) {
      await zipDir.create(recursive: true);
    }
    return zipDir.path;
  }
}
