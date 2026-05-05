/// Wallet screen — credit balance, purchase packs, transaction history.
library;

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:mobile/services/billing_service.dart';
import 'package:mobile/services/api_client.dart';

class WalletScreen extends StatefulWidget {
  const WalletScreen({super.key});

  @override
  State<WalletScreen> createState() => _WalletScreenState();
}

class _WalletScreenState extends State<WalletScreen> {
  List<Map<String, dynamic>> _history = [];
  bool _loadingHistory = true;

  @override
  void initState() {
    super.initState();
    _loadHistory();
  }

  Future<void> _loadHistory() async {
    try {
      final history = await ApiClient.getHistory();
      setState(() {
        _history = history;
        _loadingHistory = false;
      });
    } catch (e) {
      setState(() => _loadingHistory = false);
    }
  }

  Future<void> _refresh() async {
    final billing = context.read<BillingService>();
    await billing.refreshBalance();
    await _loadHistory();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF0D1117),
      appBar: AppBar(
        title: const Text('Wallet'),
        backgroundColor: const Color(0xFF161B22),
        foregroundColor: Colors.white,
        elevation: 0,
      ),
      body: Consumer<BillingService>(
        builder: (context, billing, _) {
          return RefreshIndicator(
            onRefresh: _refresh,
            color: const Color(0xFF238636),
            child: ListView(
              padding: const EdgeInsets.all(16),
              children: [
                // ---- Balance card ----
                _buildBalanceCard(billing),
                const SizedBox(height: 24),

                // ---- Buy credits ----
                const Text(
                  'BUY CREDITS',
                  style: TextStyle(
                    color: Colors.grey,
                    fontSize: 12,
                    fontWeight: FontWeight.w700,
                    letterSpacing: 1.5,
                  ),
                ),
                const SizedBox(height: 12),
                ...creditPacks.map((pack) => _buildPackCard(billing, pack)),
                const SizedBox(height: 24),

                // ---- Scan costs ----
                _buildCostTable(),
                const SizedBox(height: 24),

                // ---- History ----
                const Text(
                  'TRANSACTION HISTORY',
                  style: TextStyle(
                    color: Colors.grey,
                    fontSize: 12,
                    fontWeight: FontWeight.w700,
                    letterSpacing: 1.5,
                  ),
                ),
                const SizedBox(height: 12),
                if (_loadingHistory)
                  const Center(child: CircularProgressIndicator())
                else if (_history.isEmpty)
                  Center(
                    child: Padding(
                      padding: const EdgeInsets.all(20),
                      child: Text('No transactions yet',
                          style: TextStyle(color: Colors.grey[600])),
                    ),
                  )
                else
                  ..._history.map(_buildHistoryTile),
              ],
            ),
          );
        },
      ),
    );
  }

  Widget _buildBalanceCard(BillingService billing) {
    return Container(
      padding: const EdgeInsets.symmetric(vertical: 32, horizontal: 20),
      decoration: BoxDecoration(
        gradient: const LinearGradient(
          colors: [Color(0xFF1A3A2A), Color(0xFF0D1117)],
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
        ),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: const Color(0xFF238636).withValues(alpha: 0.3)),
      ),
      child: Column(
        children: [
          const Text(
            'CREDIT BALANCE',
            style: TextStyle(
              color: Colors.grey,
              fontSize: 12,
              fontWeight: FontWeight.w700,
              letterSpacing: 2,
            ),
          ),
          const SizedBox(height: 12),
          billing.loading
              ? const CircularProgressIndicator(color: Color(0xFF238636))
              : Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    const Icon(Icons.toll, color: Color(0xFF238636), size: 36),
                    const SizedBox(width: 12),
                    Text(
                      '${billing.balance}',
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 48,
                        fontWeight: FontWeight.w800,
                      ),
                    ),
                  ],
                ),
          if (billing.error != null)
            Padding(
              padding: const EdgeInsets.only(top: 8),
              child: Text(billing.error!,
                  style: const TextStyle(color: Colors.orange, fontSize: 12)),
            ),
        ],
      ),
    );
  }

  Widget _buildPackCard(BillingService billing, CreditPack pack) {
    return Card(
      color: const Color(0xFF161B22),
      margin: const EdgeInsets.only(bottom: 10),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      child: InkWell(
        borderRadius: BorderRadius.circular(12),
        onTap: billing.loading ? null : () => billing.purchasePack(pack),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
          child: Row(
            children: [
              Container(
                width: 44,
                height: 44,
                decoration: BoxDecoration(
                  color: const Color(0xFF238636).withValues(alpha: 0.15),
                  borderRadius: BorderRadius.circular(10),
                ),
                child:
                    const Icon(Icons.toll, color: Color(0xFF238636), size: 22),
              ),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      '${pack.credits} Credits',
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 16,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    if (pack.savings != null)
                      Text(pack.savings!,
                          style: const TextStyle(
                              color: Color(0xFF238636), fontSize: 12)),
                  ],
                ),
              ),
              Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
                decoration: BoxDecoration(
                  color: const Color(0xFF238636),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Text(
                  pack.price,
                  style: const TextStyle(
                    color: Colors.white,
                    fontWeight: FontWeight.w700,
                    fontSize: 14,
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildCostTable() {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0xFF161B22),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'SCAN COSTS',
            style: TextStyle(
              color: Colors.grey,
              fontSize: 12,
              fontWeight: FontWeight.w700,
              letterSpacing: 1.5,
            ),
          ),
          const SizedBox(height: 12),
          _costRow('Basic', '1 credit', 'Mesh + GLB + PLY'),
          _costRow('Premium', '2 credits', '+ NeuS refinement + Splat'),
          _costRow('Pro', '3 credits', '+ Primitives + E57 + IFC'),
        ],
      ),
    );
  }

  Widget _costRow(String tier, String cost, String features) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Row(
        children: [
          SizedBox(
            width: 70,
            child: Text(tier,
                style: const TextStyle(
                    color: Colors.white, fontWeight: FontWeight.w600)),
          ),
          SizedBox(
            width: 80,
            child: Text(cost,
                style: const TextStyle(color: Color(0xFF238636), fontSize: 13)),
          ),
          Expanded(
            child: Text(features,
                style: TextStyle(color: Colors.grey[500], fontSize: 12)),
          ),
        ],
      ),
    );
  }

  Widget _buildHistoryTile(Map<String, dynamic> txn) {
    final amount = txn['amount'] as int;
    final isPositive = amount > 0;
    final reason = txn['reason'] as String;
    final createdAt = txn['created_at'] as String;

    final (icon, label) = switch (reason) {
      'welcome_bonus' => (Icons.card_giftcard, 'Welcome Bonus'),
      'purchase' => (Icons.shopping_cart, 'Credit Purchase'),
      'refund' => (Icons.replay, 'Refund'),
      String r when r.startsWith('scan_') =>
        (Icons.view_in_ar, 'Scan (${r.substring(5)})'),
      _ => (Icons.receipt, reason),
    };

    return Card(
      color: const Color(0xFF161B22),
      margin: const EdgeInsets.only(bottom: 6),
      child: ListTile(
        leading: Icon(icon, color: isPositive ? const Color(0xFF238636) : const Color(0xFFDA3633), size: 20),
        title: Text(label, style: const TextStyle(color: Colors.white, fontSize: 14)),
        subtitle: Text(
          createdAt.substring(0, 16).replaceFirst('T', ' '),
          style: TextStyle(color: Colors.grey[600], fontSize: 11),
        ),
        trailing: Text(
          '${isPositive ? "+" : ""}$amount',
          style: TextStyle(
            color: isPositive ? const Color(0xFF238636) : const Color(0xFFDA3633),
            fontWeight: FontWeight.w700,
            fontSize: 16,
          ),
        ),
      ),
    );
  }
}
