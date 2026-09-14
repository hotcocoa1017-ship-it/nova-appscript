import 'package:flutter/material.dart';

import 'models/room.dart';
import 'state/app_controller.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const NovaMobileApp());
}

class NovaMobileApp extends StatefulWidget {
  const NovaMobileApp({super.key});

  @override
  State<NovaMobileApp> createState() => _NovaMobileAppState();
}

class _NovaMobileAppState extends State<NovaMobileApp>
    with WidgetsBindingObserver {
  late final AppController controller;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    controller = AppController();
    controller.bootstrap();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed && controller.isAuthenticated) {
      controller.handleAppResumed();
    }
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      title: 'NOVA WORKS',
      theme: ThemeData(
        useMaterial3: true,
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFF3157D5),
          brightness: Brightness.light,
        ),
        scaffoldBackgroundColor: const Color(0xFFF6F7FB),
        cardTheme: const CardThemeData(
          margin: EdgeInsets.zero,
          elevation: 0,
        ),
      ),
      home: AnimatedBuilder(
        animation: controller,
        builder: (context, _) {
          if (controller.bootstrapping) {
            return const _SplashScreen();
          }
          if (!controller.isAuthenticated) {
            return LoginScreen(controller: controller);
          }
          return RoommaidHomeScreen(controller: controller);
        },
      ),
    );
  }
}

class _SplashScreen extends StatelessWidget {
  const _SplashScreen();

  @override
  Widget build(BuildContext context) {
    return const Scaffold(
      body: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              'NOVA',
              style: TextStyle(fontSize: 32, fontWeight: FontWeight.w800),
            ),
            SizedBox(height: 18),
            CircularProgressIndicator(),
          ],
        ),
      ),
    );
  }
}

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key, required this.controller});
  final AppController controller;

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final nameController = TextEditingController();
  final employeeController = TextEditingController();
  String site = '쏘라노';

  @override
  void dispose() {
    nameController.dispose();
    employeeController.dispose();
    super.dispose();
  }

  Future<void> _login() async {
    FocusScope.of(context).unfocus();
    await widget.controller.login(
      name: nameController.text,
      employeeNo: employeeController.text,
      site: site,
    );
  }

  @override
  Widget build(BuildContext context) {
    final busy = widget.controller.signingIn;
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(24),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 440),
              child: Card(
                child: Padding(
                  padding: const EdgeInsets.all(24),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      const Text(
                        'NOVA WORKS',
                        textAlign: TextAlign.center,
                        style: TextStyle(
                          fontSize: 28,
                          fontWeight: FontWeight.w800,
                          letterSpacing: -0.8,
                        ),
                      ),
                      const SizedBox(height: 6),
                      Text(
                        'ROOMMAID · Core 3.0 Alpha',
                        textAlign: TextAlign.center,
                        style: TextStyle(color: Colors.grey.shade600),
                      ),
                      const SizedBox(height: 28),
                      TextField(
                        controller: nameController,
                        textInputAction: TextInputAction.next,
                        decoration: const InputDecoration(
                          labelText: '이름',
                          border: OutlineInputBorder(),
                        ),
                      ),
                      const SizedBox(height: 14),
                      TextField(
                        controller: employeeController,
                        keyboardType: TextInputType.number,
                        textInputAction: TextInputAction.done,
                        onSubmitted: (_) => busy ? null : _login(),
                        decoration: const InputDecoration(
                          labelText: '사번',
                          border: OutlineInputBorder(),
                        ),
                      ),
                      const SizedBox(height: 14),
                      SegmentedButton<String>(
                        segments: const [
                          ButtonSegment(value: '쏘라노', label: Text('쏘라노')),
                          ButtonSegment(value: '별관', label: Text('별관')),
                        ],
                        selected: {site},
                        onSelectionChanged: busy
                            ? null
                            : (value) => setState(() => site = value.first),
                      ),
                      if (widget.controller.globalError != null) ...[
                        const SizedBox(height: 14),
                        Text(
                          widget.controller.globalError!,
                          textAlign: TextAlign.center,
                          style: TextStyle(color: Theme.of(context).colorScheme.error),
                        ),
                      ],
                      const SizedBox(height: 22),
                      FilledButton(
                        onPressed: busy ? null : _login,
                        style: FilledButton.styleFrom(
                          minimumSize: const Size.fromHeight(54),
                        ),
                        child: busy
                            ? const SizedBox(
                                width: 22,
                                height: 22,
                                child: CircularProgressIndicator(strokeWidth: 2),
                              )
                            : const Text('로그인'),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class RoommaidHomeScreen extends StatelessWidget {
  const RoommaidHomeScreen({super.key, required this.controller});
  final AppController controller;

  Future<void> _runAction(
    BuildContext context,
    NovaRoom room,
    String action,
  ) async {
    final ok = await controller.performAction(room, action);
    if (!context.mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(ok
            ? (action == 'CLEANING_START' ? '${room.roomNo}호 청소를 시작했습니다.' : '${room.roomNo}호 청소완료를 저장했습니다.')
            : (controller.globalError ?? '처리하지 못했습니다.')),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final user = controller.user!;
    return Scaffold(
      appBar: AppBar(
        title: const Text('오늘의 객실'),
        actions: [
          IconButton(
            tooltip: '새로고침',
            onPressed: controller.loadingRooms ? null : controller.refreshRooms,
            icon: const Icon(Icons.refresh),
          ),
          PopupMenuButton<String>(
            onSelected: (value) {
              if (value == 'logout') controller.logout();
            },
            itemBuilder: (_) => const [
              PopupMenuItem(value: 'logout', child: Text('로그아웃')),
            ],
          ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: controller.refreshRooms,
        child: ListView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: const EdgeInsets.fromLTRB(16, 8, 16, 28),
          children: [
            _SummaryCard(
              name: user.name,
              site: user.sessionSite,
              businessDate: controller.businessDate,
              roomCount: controller.rooms.length,
            ),
            if (controller.globalError != null) ...[
              const SizedBox(height: 12),
              _ErrorBanner(message: controller.globalError!),
            ],
            const SizedBox(height: 14),
            if (controller.loadingRooms)
              const LinearProgressIndicator()
            else if (controller.rooms.isEmpty)
              const _EmptyRooms()
            else
              ...controller.rooms.map(
                (room) => Padding(
                  padding: const EdgeInsets.only(bottom: 12),
                  child: _RoomCard(
                    room: room,
                    pending: controller.pendingRoomNos.contains(room.roomNo),
                    onStart: () => _runAction(context, room, 'CLEANING_START'),
                    onComplete: () => _runAction(context, room, 'CLEANING_COMPLETE'),
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }
}

class _SummaryCard extends StatelessWidget {
  const _SummaryCard({
    required this.name,
    required this.site,
    required this.businessDate,
    required this.roomCount,
  });

  final String name;
  final String site;
  final String businessDate;
  final int roomCount;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(18),
        child: Row(
          children: [
            CircleAvatar(
              radius: 24,
              child: Text(name.isEmpty ? '?' : name.characters.first),
            ),
            const SizedBox(width: 14),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(name, style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w700)),
                  const SizedBox(height: 4),
                  Text('$site · $businessDate'),
                ],
              ),
            ),
            Column(
              children: [
                Text('$roomCount', style: const TextStyle(fontSize: 26, fontWeight: FontWeight.w800)),
                const Text('배정실'),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _RoomCard extends StatelessWidget {
  const _RoomCard({
    required this.room,
    required this.pending,
    required this.onStart,
    required this.onComplete,
  });

  final NovaRoom room;
  final bool pending;
  final VoidCallback onStart;
  final VoidCallback onComplete;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(
                    '${room.roomNo}호',
                    style: const TextStyle(fontSize: 24, fontWeight: FontWeight.w800),
                  ),
                ),
                _StatusChip(status: room.cleaningStatus),
              ],
            ),
            const SizedBox(height: 8),
            Text('${room.building} · ${room.roomStatus} · v${room.version}'),
            if (room.operationalStatus.isNotEmpty) ...[
              const SizedBox(height: 4),
              Text('운영상태: ${room.operationalStatus}'),
            ],
            const SizedBox(height: 16),
            if (pending)
              const Center(child: CircularProgressIndicator())
            else if (room.canStartCleaning)
              FilledButton.icon(
                onPressed: onStart,
                icon: const Icon(Icons.play_arrow_rounded),
                label: const Text('청소 시작'),
                style: FilledButton.styleFrom(minimumSize: const Size.fromHeight(52)),
              )
            else if (room.canCompleteCleaning)
              FilledButton.icon(
                onPressed: onComplete,
                icon: const Icon(Icons.check_rounded),
                label: const Text('청소 완료'),
                style: FilledButton.styleFrom(minimumSize: const Size.fromHeight(52)),
              )
            else
              OutlinedButton(
                onPressed: null,
                style: OutlinedButton.styleFrom(minimumSize: const Size.fromHeight(52)),
                child: Text(_statusLabel(room.cleaningStatus)),
              ),
          ],
        ),
      ),
    );
  }
}

class _StatusChip extends StatelessWidget {
  const _StatusChip({required this.status});
  final String status;

  @override
  Widget build(BuildContext context) {
    return Chip(label: Text(_statusLabel(status)));
  }
}

class _ErrorBanner extends StatelessWidget {
  const _ErrorBanner({required this.message});
  final String message;

  @override
  Widget build(BuildContext context) {
    return Material(
      borderRadius: BorderRadius.circular(12),
      color: Theme.of(context).colorScheme.errorContainer,
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Text(message),
      ),
    );
  }
}

class _EmptyRooms extends StatelessWidget {
  const _EmptyRooms();

  @override
  Widget build(BuildContext context) {
    return const Padding(
      padding: EdgeInsets.symmetric(vertical: 70),
      child: Column(
        children: [
          Icon(Icons.hotel_outlined, size: 52),
          SizedBox(height: 12),
          Text('현재 배정된 객실이 없습니다.'),
        ],
      ),
    );
  }
}

String _statusLabel(String status) {
  switch (status) {
    case 'WAITING':
      return '대기';
    case 'ASSIGNED':
      return '배정';
    case 'CLEANING':
      return '청소중';
    case 'COMPLETED':
      return '청소완료';
    case 'QM_WAITING':
      return '점검대기';
    case 'QM_CHECKING':
      return '점검중';
    case 'QM_COMPLETED':
      return '점검완료';
    case 'REWORK':
      return '재정비';
    default:
      return status.isEmpty ? '상태없음' : status;
  }
}
