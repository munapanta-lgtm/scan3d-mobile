import 'dart:io' show Platform;
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'features/home/home_screen.dart';
import 'features/wallet/wallet_screen.dart';
import 'services/billing_service.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();

  // Use FFI-based SQLite on desktop (Windows/Linux/macOS).
  // On Android/iOS, sqflite uses native plugins automatically.
  if (Platform.isWindows || Platform.isLinux || Platform.isMacOS) {
    sqfliteFfiInit();
    databaseFactory = databaseFactoryFfi;
  }

  runApp(const Scan3DApp());
}

class Scan3DApp extends StatelessWidget {
  const Scan3DApp({super.key});

  @override
  Widget build(BuildContext context) {
    return ChangeNotifierProvider(
      create: (_) => BillingService(),
      child: MaterialApp(
        title: 'SCAN3D',
        debugShowCheckedModeBanner: false,
        theme: ThemeData(
          brightness: Brightness.dark,
          scaffoldBackgroundColor: const Color(0xFF0D1117),
          colorSchemeSeed: const Color(0xFF238636),
          useMaterial3: true,
          fontFamily: 'Roboto',
        ),
        home: const MainNavigation(),
      ),
    );
  }
}

/// Bottom navigation: Home | Wallet
class MainNavigation extends StatefulWidget {
  const MainNavigation({super.key});

  @override
  State<MainNavigation> createState() => _MainNavigationState();
}

class _MainNavigationState extends State<MainNavigation> {
  int _currentIndex = 0;

  final _pages = const [
    HomeScreen(),
    WalletScreen(),
  ];

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: IndexedStack(
        index: _currentIndex,
        children: _pages,
      ),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _currentIndex,
        onDestinationSelected: (i) => setState(() => _currentIndex = i),
        backgroundColor: const Color(0xFF161B22),
        indicatorColor: const Color(0xFF238636).withValues(alpha: 0.2),
        destinations: [
          const NavigationDestination(
            icon: Icon(Icons.view_in_ar_outlined),
            selectedIcon: Icon(Icons.view_in_ar, color: Color(0xFF238636)),
            label: 'Scans',
          ),
          NavigationDestination(
            icon: const Icon(Icons.account_balance_wallet_outlined),
            selectedIcon: const Icon(Icons.account_balance_wallet,
                color: Color(0xFF238636)),
            label: 'Wallet',
          ),
        ],
      ),
    );
  }
}
