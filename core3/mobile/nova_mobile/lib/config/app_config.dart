class AppConfig {
  static const apiBaseUrl = String.fromEnvironment(
    'NOVA_API_BASE_URL',
    defaultValue: 'https://nova-core3-api-dev-479836905263.asia-southeast1.run.app',
  );

  static const requestTimeout = Duration(seconds: 8);
  static const roomReconcileInterval = Duration(seconds: 15);

  static DateTime koreaNow() => DateTime.now().toUtc().add(const Duration(hours: 9));

  static String businessDate() {
    final now = koreaNow();
    final y = now.year.toString().padLeft(4, '0');
    final m = now.month.toString().padLeft(2, '0');
    final d = now.day.toString().padLeft(2, '0');
    return '$y-$m-$d';
  }
}
