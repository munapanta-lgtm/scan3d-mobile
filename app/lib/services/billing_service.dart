/// Google Play Billing wrapper with mock mode for testing.
library;

import 'dart:async';
import 'dart:io' show Platform;
import 'package:flutter/foundation.dart';
import 'package:in_app_purchase/in_app_purchase.dart';
import 'package:mobile/services/api_client.dart';

/// Credit packs available for purchase.
class CreditPack {
  final String productId;
  final int credits;
  final String price;
  final String? savings;

  const CreditPack({
    required this.productId,
    required this.credits,
    required this.price,
    this.savings,
  });
}

const creditPacks = [
  CreditPack(productId: 'credits_10', credits: 10, price: '\$4.99'),
  CreditPack(
      productId: 'credits_50',
      credits: 50,
      price: '\$19.99',
      savings: 'Save 20%'),
  CreditPack(
      productId: 'credits_200',
      credits: 200,
      price: '\$59.99',
      savings: 'Save 40%'),
];

class BillingService extends ChangeNotifier {
  int _balance = 0;
  bool _loading = true;
  String? _error;
  StreamSubscription<List<PurchaseDetails>>? _subscription;

  int get balance => _balance;
  bool get loading => _loading;
  String? get error => _error;

  BillingService() {
    _init();
  }

  Future<void> _init() async {
    // Listen to purchase stream on Android
    if (!kIsWeb && Platform.isAndroid) {
      final iap = InAppPurchase.instance;
      final available = await iap.isAvailable();
      if (available) {
        _subscription = iap.purchaseStream.listen(_onPurchaseUpdate);
      }
    }
    await refreshBalance();
  }

  Future<void> refreshBalance() async {
    _loading = true;
    _error = null;
    notifyListeners();

    try {
      _balance = await ApiClient.getBalance();
    } catch (e) {
      // Offline fallback: show cached or 0
      _error = 'Could not reach server';
      debugPrint('[billing] Balance fetch failed: $e');
    }

    _loading = false;
    notifyListeners();
  }

  /// Start a purchase flow.
  Future<void> purchasePack(CreditPack pack) async {
    if (!kIsWeb && Platform.isAndroid) {
      final iap = InAppPurchase.instance;
      final available = await iap.isAvailable();

      if (available) {
        // Real Google Play purchase
        final response =
            await iap.queryProductDetails({pack.productId});
        if (response.productDetails.isEmpty) {
          // Product not configured in Google Play Console yet — use mock
          await _mockPurchase(pack);
          return;
        }
        final product = response.productDetails.first;
        final param = PurchaseParam(productDetails: product);
        await iap.buyConsumable(purchaseParam: param);
        return;
      }
    }

    // Desktop / unavailable: mock purchase
    await _mockPurchase(pack);
  }

  /// Mock purchase for development/testing.
  Future<void> _mockPurchase(CreditPack pack) async {
    _loading = true;
    notifyListeners();

    try {
      _balance = await ApiClient.recordPurchase(pack.productId);
    } catch (e) {
      _error = 'Purchase failed: $e';
    }

    _loading = false;
    notifyListeners();
  }

  /// Handle completed purchases from Google Play.
  void _onPurchaseUpdate(List<PurchaseDetails> purchases) async {
    for (final purchase in purchases) {
      if (purchase.status == PurchaseStatus.purchased ||
          purchase.status == PurchaseStatus.restored) {
        // Verify + record on backend
        try {
          _balance = await ApiClient.recordPurchase(purchase.productID);
        } catch (e) {
          debugPrint('[billing] Record purchase failed: $e');
        }

        // Complete the purchase on Google Play
        if (purchase.pendingCompletePurchase) {
          await InAppPurchase.instance.completePurchase(purchase);
        }
      } else if (purchase.status == PurchaseStatus.error) {
        _error = 'Purchase error: ${purchase.error?.message}';
      }

      notifyListeners();
    }
  }

  @override
  void dispose() {
    _subscription?.cancel();
    super.dispose();
  }
}
