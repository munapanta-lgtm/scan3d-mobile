/// API client for the SCAN3D backend.
library;

import 'dart:convert';
import 'package:http/http.dart' as http;

// TODO: Replace with production URL
const _baseUrl = 'http://10.0.2.2:8000'; // Android emulator → host localhost
// const _baseUrl = 'http://192.168.x.x:8000'; // Physical device → host LAN IP

class ApiClient {
  static const userId = 'default_user'; // MVP — no auth yet

  // --- Credits ---------------------------------------------------------------

  static Future<int> getBalance() async {
    final resp = await http.get(Uri.parse('$_baseUrl/credits/$userId/balance'));
    if (resp.statusCode != 200) throw Exception('Failed to get balance');
    final data = jsonDecode(resp.body);
    return data['balance'] as int;
  }

  static Future<List<Map<String, dynamic>>> getHistory() async {
    final resp = await http.get(Uri.parse('$_baseUrl/credits/$userId/history'));
    if (resp.statusCode != 200) throw Exception('Failed to get history');
    final data = jsonDecode(resp.body);
    return List<Map<String, dynamic>>.from(data['transactions']);
  }

  static Future<int> recordPurchase(String productId) async {
    final resp = await http.post(
      Uri.parse('$_baseUrl/credits/$userId/purchase'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({
        'user_id': userId,
        'product_id': productId,
      }),
    );
    if (resp.statusCode != 200) throw Exception('Purchase recording failed');
    final data = jsonDecode(resp.body);
    return data['balance'] as int;
  }

  // --- Scans -----------------------------------------------------------------

  static Future<String> getUploadUrl(String scanId) async {
    final resp = await http.post(
      Uri.parse('$_baseUrl/scans/upload-url'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'scan_id': scanId}),
    );
    if (resp.statusCode != 200) throw Exception('Failed to get upload URL');
    final data = jsonDecode(resp.body);
    return data['upload_url'] as String;
  }

  static Future<Map<String, dynamic>> processScan(
    String scanId, {
    String scanType = 'basic',
    double tagSize = 0.167,
  }) async {
    final resp = await http.post(
      Uri.parse('$_baseUrl/scans/$scanId/process'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({
        'tag_size': tagSize,
        'scan_type': scanType,
        'user_id': userId,
      }),
    );
    if (resp.statusCode == 402) {
      throw InsufficientCreditsException(
        jsonDecode(resp.body)['detail']['message'] ?? 'Insufficient credits',
      );
    }
    if (resp.statusCode != 200) throw Exception('Failed to process scan');
    return jsonDecode(resp.body) as Map<String, dynamic>;
  }

  static Future<Map<String, dynamic>> getScanStatus(String scanId) async {
    final resp = await http.get(Uri.parse('$_baseUrl/scans/$scanId/status'));
    if (resp.statusCode != 200) throw Exception('Failed to get status');
    return jsonDecode(resp.body) as Map<String, dynamic>;
  }

  static Future<List<Map<String, dynamic>>> getScanResults(String scanId) async {
    final resp = await http.get(Uri.parse('$_baseUrl/scans/$scanId/results'));
    if (resp.statusCode != 200) return [];
    final data = jsonDecode(resp.body);
    return List<Map<String, dynamic>>.from(data['files']);
  }
}

class InsufficientCreditsException implements Exception {
  final String message;
  InsufficientCreditsException(this.message);
  @override
  String toString() => message;
}
