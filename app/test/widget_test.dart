import 'package:flutter_test/flutter_test.dart';
import 'package:mobile/main.dart';

void main() {
  testWidgets('App launches without error', (WidgetTester tester) async {
    await tester.pumpWidget(const Scan3DApp());
    expect(find.text('SCAN3D'), findsOneWidget);
  });
}
