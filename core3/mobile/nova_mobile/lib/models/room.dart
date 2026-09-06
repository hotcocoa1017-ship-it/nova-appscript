class NovaRoom {
  const NovaRoom({
    required this.businessDate,
    required this.site,
    required this.roomNo,
    required this.building,
    required this.roomStatus,
    required this.cleaningStatus,
    required this.cleaningType,
    required this.assignmentType,
    required this.roommaidEmployeeNo,
    required this.secondaryRoommaidEmployeeNo,
    required this.qmEmployeeNo,
    required this.operationalStatus,
    required this.version,
    this.cleaningStartedAt,
    this.cleaningCompletedAt,
    this.updatedAt,
  });

  final String businessDate;
  final String site;
  final String roomNo;
  final String building;
  final String roomStatus;
  final String cleaningStatus;
  final String cleaningType;
  final String assignmentType;
  final String roommaidEmployeeNo;
  final String secondaryRoommaidEmployeeNo;
  final String qmEmployeeNo;
  final String operationalStatus;
  final int version;
  final String? cleaningStartedAt;
  final String? cleaningCompletedAt;
  final String? updatedAt;

  factory NovaRoom.fromJson(Map<String, dynamic> json) {
    return NovaRoom(
      businessDate: '${json['businessDate'] ?? ''}'.trim(),
      site: '${json['site'] ?? ''}'.trim(),
      roomNo: '${json['roomNo'] ?? ''}'.trim(),
      building: '${json['building'] ?? ''}'.trim(),
      roomStatus: '${json['roomStatus'] ?? ''}'.trim().toUpperCase(),
      cleaningStatus: '${json['cleaningStatus'] ?? ''}'.trim().toUpperCase(),
      cleaningType: '${json['cleaningType'] ?? ''}'.trim().toUpperCase(),
      assignmentType: '${json['assignmentType'] ?? ''}'.trim().toUpperCase(),
      roommaidEmployeeNo: '${json['roommaidEmployeeNo'] ?? ''}'.trim(),
      secondaryRoommaidEmployeeNo:
          '${json['secondaryRoommaidEmployeeNo'] ?? ''}'.trim(),
      qmEmployeeNo: '${json['qmEmployeeNo'] ?? ''}'.trim(),
      operationalStatus: '${json['operationalStatus'] ?? ''}'.trim(),
      version: (json['version'] as num?)?.toInt() ?? 0,
      cleaningStartedAt: json['cleaningStartedAt']?.toString(),
      cleaningCompletedAt: json['cleaningCompletedAt']?.toString(),
      updatedAt: json['updatedAt']?.toString(),
    );
  }

  NovaRoom copyWith({
    String? cleaningStatus,
    int? version,
  }) {
    return NovaRoom(
      businessDate: businessDate,
      site: site,
      roomNo: roomNo,
      building: building,
      roomStatus: roomStatus,
      cleaningStatus: cleaningStatus ?? this.cleaningStatus,
      cleaningType: cleaningType,
      assignmentType: assignmentType,
      roommaidEmployeeNo: roommaidEmployeeNo,
      secondaryRoommaidEmployeeNo: secondaryRoommaidEmployeeNo,
      qmEmployeeNo: qmEmployeeNo,
      operationalStatus: operationalStatus,
      version: version ?? this.version,
      cleaningStartedAt: cleaningStartedAt,
      cleaningCompletedAt: cleaningCompletedAt,
      updatedAt: updatedAt,
    );
  }

  bool get canStartCleaning =>
      roomStatus != 'DUE_OUT' &&
      const {'WAITING', 'ASSIGNED', 'REWORK'}.contains(cleaningStatus);

  bool get canCompleteCleaning => cleaningStatus == 'CLEANING';

  bool isDesiredFor(String action) {
    if (action == 'CLEANING_START') return cleaningStatus == 'CLEANING';
    if (action == 'CLEANING_COMPLETE') {
      return const {'COMPLETED', 'QM_WAITING', 'QM_CHECKING', 'QM_COMPLETED'}
          .contains(cleaningStatus);
    }
    return false;
  }
}
