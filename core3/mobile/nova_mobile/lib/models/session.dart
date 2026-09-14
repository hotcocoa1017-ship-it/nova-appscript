class NovaUser {
  const NovaUser({
    required this.employeeNo,
    required this.name,
    required this.role,
    required this.sessionSite,
    this.defaultSite = '',
    this.allowedSites = const [],
  });

  final String employeeNo;
  final String name;
  final String role;
  final String sessionSite;
  final String defaultSite;
  final List<String> allowedSites;

  factory NovaUser.fromJson(Map<String, dynamic> json) {
    return NovaUser(
      employeeNo: '${json['employeeNo'] ?? ''}'.trim(),
      name: '${json['name'] ?? ''}'.trim(),
      role: '${json['role'] ?? ''}'.trim().toUpperCase(),
      sessionSite: '${json['sessionSite'] ?? ''}'.trim(),
      defaultSite: '${json['defaultSite'] ?? ''}'.trim(),
      allowedSites: (json['allowedSites'] as List<dynamic>? ?? const [])
          .map((value) => '$value'.trim())
          .where((value) => value.isNotEmpty)
          .toList(growable: false),
    );
  }

  Map<String, dynamic> toJson() => {
        'employeeNo': employeeNo,
        'name': name,
        'role': role,
        'sessionSite': sessionSite,
        'defaultSite': defaultSite,
        'allowedSites': allowedSites,
      };
}

class NovaSession {
  const NovaSession({
    required this.accessToken,
    required this.expiresAt,
    required this.user,
  });

  final String accessToken;
  final String expiresAt;
  final NovaUser user;

  factory NovaSession.fromLoginJson(Map<String, dynamic> json) {
    final userJson = json['user'];
    if (json['ok'] != true || userJson is! Map<String, dynamic>) {
      throw const FormatException('invalid NOVA login payload');
    }
    return NovaSession(
      accessToken: '${json['accessToken'] ?? ''}'.trim(),
      expiresAt: '${json['expiresAt'] ?? ''}'.trim(),
      user: NovaUser.fromJson(userJson),
    );
  }

  Map<String, dynamic> toJson() => {
        'accessToken': accessToken,
        'expiresAt': expiresAt,
        'user': user.toJson(),
      };

  factory NovaSession.fromJson(Map<String, dynamic> json) {
    return NovaSession(
      accessToken: '${json['accessToken'] ?? ''}'.trim(),
      expiresAt: '${json['expiresAt'] ?? ''}'.trim(),
      user: NovaUser.fromJson(
        Map<String, dynamic>.from(json['user'] as Map? ?? const {}),
      ),
    );
  }

  NovaSession withVerifiedUser(NovaUser verifiedUser) => NovaSession(
        accessToken: accessToken,
        expiresAt: expiresAt,
        user: verifiedUser,
      );
}
