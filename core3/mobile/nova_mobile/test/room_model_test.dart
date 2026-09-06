import 'package:flutter_test/flutter_test.dart';
import 'package:nova_mobile/models/room.dart';

NovaRoom room({
  String roomStatus = 'CHECKED_OUT',
  String cleaningStatus = 'WAITING',
  String qmEmployeeNo = '',
}) {
  return NovaRoom.fromJson({
    'businessDate': '2026-09-06',
    'site': '쏘라노',
    'roomNo': '7217',
    'building': '7동',
    'roomStatus': roomStatus,
    'cleaningStatus': cleaningStatus,
    'cleaningType': 'NORMAL',
    'assignmentType': 'SOLO',
    'roommaidEmployeeNo': '321516',
    'secondaryRoommaidEmployeeNo': '',
    'qmEmployeeNo': qmEmployeeNo,
    'operationalStatus': '',
    'version': 3,
  });
}

void main() {
  test('WAITING checked-out room can start cleaning', () {
    expect(room().canStartCleaning, isTrue);
  });

  test('DUE_OUT room cannot start cleaning', () {
    expect(room(roomStatus: 'DUE_OUT').canStartCleaning, isFalse);
  });

  test('CLEANING room can complete', () {
    expect(room(cleaningStatus: 'CLEANING').canCompleteCleaning, isTrue);
  });

  test('semantic completion convergence accepts QM states', () {
    for (final status in ['COMPLETED', 'QM_WAITING', 'QM_CHECKING', 'QM_COMPLETED']) {
      expect(room(cleaningStatus: status).isDesiredFor('CLEANING_COMPLETE'), isTrue);
    }
  });
}
