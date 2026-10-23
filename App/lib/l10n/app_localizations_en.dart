// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for English (`en`).
class AppLocalizationsEn extends AppLocalizations {
  AppLocalizationsEn([String locale = 'en']) : super(locale);

  @override
  String get appTitle => 'Moisture';

  @override
  String get navPlants => 'Plants';

  @override
  String get navDevices => 'Devices';

  @override
  String get navAlerts => 'Alerts';

  @override
  String get navSettings => 'Settings';

  @override
  String get roleViewer => 'Viewer';

  @override
  String get roleMember => 'Member';

  @override
  String get roleAdmin => 'Admin';

  @override
  String get roleOwner => 'Owner';

  @override
  String get noPlantsTitle => 'Start with your first plant';

  @override
  String get retry => 'Retry';

  @override
  String get errorGeneric => 'Something went wrong.';

  @override
  String get errorForbidden => 'Your role no longer allows this.';

  @override
  String get errorSafetyLimit => 'That\'s longer than this pump\'s limit.';

  @override
  String get errorBusy => 'The device is busy. Try again shortly.';

  @override
  String moistureSemantics(int percent) {
    return 'Moisture $percent percent';
  }

  @override
  String percentValue(int value) {
    return '$value %';
  }

  @override
  String secondsValue(int value) {
    return '$value s';
  }

  @override
  String hoursValue(int value) {
    return '$value h';
  }

  @override
  String get justNow => 'just now';

  @override
  String minutesAgo(int n) {
    return '$n min ago';
  }

  @override
  String hoursAgo(int n) {
    return '$n h ago';
  }

  @override
  String daysAgo(int n) {
    return '$n d ago';
  }

  @override
  String get deviceOnline => 'Online';

  @override
  String get deviceLate => 'Late';

  @override
  String get deviceOffline => 'Offline';

  @override
  String lastSeen(String ago) {
    return 'last seen $ago';
  }

  @override
  String lastReading(String ago) {
    return 'Last reading $ago';
  }

  @override
  String get trendFalling => 'Drying';

  @override
  String get trendSteady => 'Steady';

  @override
  String get trendRising => 'Rising';

  @override
  String get pendingCommand => 'Watering pending';

  @override
  String get waterNow => 'Water now';

  @override
  String waterFor(int seconds) {
    return 'Water for $seconds s';
  }

  @override
  String waterSheetTitle(String plant) {
    return 'Water $plant';
  }

  @override
  String get waterSheetHint =>
      'Watering starts as soon as the module confirms. If it is offline, it is sent when it is back.';

  @override
  String pumpLimit(int seconds) {
    return 'Pump limit: $seconds s';
  }

  @override
  String get waterQueued => 'Watering queued';

  @override
  String get cancel => 'Cancel';

  @override
  String get cancelCommand => 'Cancel watering';

  @override
  String get cancelCommandHint => 'Best effort — it may already have run.';

  @override
  String commandTitle(int seconds) {
    return '$seconds s watering';
  }

  @override
  String commandRunning(String time) {
    return 'Running until $time';
  }

  @override
  String get commandDone => 'Done';

  @override
  String get commandFailed => 'Failed';

  @override
  String get commandExpired => 'Expired';

  @override
  String get commandCancelled => 'Cancelled';

  @override
  String get originUser => 'Manual';

  @override
  String get originRule => 'Rule';

  @override
  String get historyTitle => 'Moisture history';

  @override
  String get range24h => '24 h';

  @override
  String get range7d => '7 d';

  @override
  String get range30d => '30 d';

  @override
  String get range1y => '1 y';

  @override
  String chartSummary(int min, int max) {
    return 'Moisture between $min and $max % in this period';
  }

  @override
  String get commandsTitle => 'Watering';

  @override
  String get noCommands => 'No watering yet.';

  @override
  String get rulesTitle => 'Rules';

  @override
  String get noRules => 'Add a rule to water automatically.';

  @override
  String get addRule => 'Add rule';

  @override
  String get editRule => 'Edit rule';

  @override
  String ruleSummary(int percent, int seconds, int hours) {
    return 'Below $percent %: water $seconds s, at most every $hours h';
  }

  @override
  String get ruleBelow => 'Water when moisture is below';

  @override
  String get ruleDuration => 'Watering duration';

  @override
  String get ruleInterval => 'At most every';

  @override
  String get ruleEnabled => 'Rule enabled';

  @override
  String get save => 'Save';

  @override
  String get delete => 'Delete';

  @override
  String get noDevices => 'Add your first device';

  @override
  String firmwareValue(String version) {
    return 'Firmware $version';
  }

  @override
  String get configInSync => 'Config in sync';

  @override
  String configPending(int rev) {
    return 'Config pending (rev $rev)';
  }

  @override
  String get configRejected => 'Config rejected';

  @override
  String get deviceDetails => 'Details';

  @override
  String get board => 'Board';

  @override
  String get slots => 'Slots';

  @override
  String slotLabel(int index) {
    return 'Slot $index';
  }

  @override
  String get identify => 'Identify';

  @override
  String get reboot => 'Reboot';

  @override
  String get deviceActionSent => 'Sent to the device.';

  @override
  String get openAlerts => 'Open';

  @override
  String get closedAlerts => 'Closed';

  @override
  String get noAlerts => 'All plants are fine';

  @override
  String alertDeviceOffline(String subject) {
    return '$subject is offline';
  }

  @override
  String alertBatteryLow(String subject) {
    return '$subject: battery low';
  }

  @override
  String alertSensorSuspect(String subject) {
    return '$subject: sensor readings look wrong';
  }

  @override
  String alertCommandFailed(String subject) {
    return '$subject: watering failed';
  }

  @override
  String get acknowledge => 'Acknowledge';

  @override
  String acknowledgedAgo(String ago) {
    return 'Acknowledged $ago';
  }

  @override
  String get appearance => 'Appearance';

  @override
  String get themeSystem => 'System';

  @override
  String get themeLight => 'Light';

  @override
  String get themeDark => 'Dark';

  @override
  String get language => 'Language';

  @override
  String get timezone => 'Time zone';

  @override
  String get demoSection => 'Demo';

  @override
  String get demoRole => 'Demo role in this household';

  @override
  String get demoRoleHint => 'Only in the dev build without a backend.';

  @override
  String get notAllowed => 'Your role doesn\'t allow this.';

  @override
  String get signal => 'Signal';

  @override
  String get firmware => 'Firmware';

  @override
  String get noReading => 'No reading yet';

  @override
  String alertOther(String subject, String kind) {
    return '$subject: $kind';
  }

  @override
  String get gatewayClock => 'Clock';

  @override
  String get gatewayClockOk => 'Synced';

  @override
  String get gatewayClockBad => 'Not synced: no automatic watering';

  @override
  String get errorReauth => 'Sign in again to do this.';

  @override
  String get serverTitle => 'Server';

  @override
  String get connSearching => 'Looking for the server on your network …';

  @override
  String get connUnreachable => 'Can\'t reach the server.';

  @override
  String get connChoose => 'Several servers found. Choose one.';

  @override
  String get connEnterAddress => 'Enter address';

  @override
  String get serverCurrent => 'Connected to';

  @override
  String get serverFound => 'Servers on your network';

  @override
  String get serverSearchAgain => 'Search again';

  @override
  String get serverAddress => 'Server address';

  @override
  String get serverAddressHint => '192.168.1.10:8000';

  @override
  String get serverAddressInvalid => 'That is not a valid address.';

  @override
  String get serverAddressNotLocal =>
      'Only addresses on your home network are allowed.';

  @override
  String get serverAddressNoAnswer => 'No Moisture server answers there.';

  @override
  String get serverAuthDev => 'Dev login (no password)';

  @override
  String get serverAuthFirebase => 'Firebase login';

  @override
  String get serverDevWarningTitle => 'Unsigned dev login';

  @override
  String get serverDevWarningBody =>
      'This server accepts logins without a password. Only continue if it is your own development server.';

  @override
  String get serverContinue => 'Connect';

  @override
  String get serverUseThis => 'Use this server';

  @override
  String get commandQueued => 'Queued';

  @override
  String signalValue(int quality) {
    return 'Link quality $quality';
  }

  @override
  String get noPlantsBody =>
      'Create a plant for a sensor of one of your devices.';

  @override
  String get serverSubtitle => 'The gateway this app talks to';

  @override
  String get gatewayTitle => 'Gateway';

  @override
  String get commandDelivered => 'Running';

  @override
  String get account => 'Account';

  @override
  String get addDevice => 'Add device';

  @override
  String get addPlant => 'Add plant';

  @override
  String get editPlant => 'Edit plant';

  @override
  String get plantName => 'Name';

  @override
  String get plantSensor => 'Moisture sensor';

  @override
  String get plantPump => 'Pump';

  @override
  String get plantNoSlots =>
      'No device has a sensor or pump configured yet. Set up a device first.';

  @override
  String alertSafeMode(String subject) {
    return '$subject is in safe mode';
  }

  @override
  String get alertZigbeeOffline => 'Zigbee is not running';

  @override
  String get auditTitle => 'Activity';

  @override
  String get noAudit => 'Nothing yet.';

  @override
  String get backupTitle => 'Backup';

  @override
  String get backupBody =>
      'Makes a consistent copy of the gateway databases on the gateway. The Zigbee network data has to be copied separately (scripts/backup.sh).';

  @override
  String get backupNow => 'Back up now';

  @override
  String get backupDone => 'Backup written on the gateway.';

  @override
  String get bannerHubDown =>
      'The watering service is not reachable. You see the last known data; changes are not possible.';

  @override
  String get bannerZigbeeDown =>
      'Zigbee is not running. Data and commands are paused.';

  @override
  String get batteryThreshold => 'Battery low (mV)';

  @override
  String get calDry => 'Dry value (raw)';

  @override
  String get calWet => 'Wet value (raw)';

  @override
  String get changePassword => 'Change password';

  @override
  String get currentPassword => 'Current password';

  @override
  String get newPassword => 'New password';

  @override
  String get passwordChangeHint => 'Changing it signs out your other devices.';

  @override
  String get passwordChanged => 'Password changed.';

  @override
  String get changeRole => 'Change role';

  @override
  String get channelApp => 'In the app';

  @override
  String get channelTelegram => 'Telegram';

  @override
  String get clearSafeMode => 'Clear safe mode';

  @override
  String get commandQueuedOffline => 'Queued · device offline';

  @override
  String get configApplyNote =>
      'The change is applied as soon as the device confirms it.';

  @override
  String get configConflict =>
      'Someone else changed this device meanwhile. The current configuration was loaded; please check and save again.';

  @override
  String get configNoBoard => 'This device has not reported its board yet.';

  @override
  String configPendingBody(int rev) {
    return 'Revision $rev is waiting for the device to confirm it.';
  }

  @override
  String configRejectedBody(String error) {
    return 'The device rejected the configuration: $error';
  }

  @override
  String get configRevert => 'Use the running configuration';

  @override
  String get configRevision => 'Configuration (running / sent)';

  @override
  String get configSaved => 'Configuration sent to the device.';

  @override
  String get confirm => 'Confirm';

  @override
  String get copied => 'Copied.';

  @override
  String get copyLink => 'Copy link';

  @override
  String get createInvite => 'Create invite';

  @override
  String get dataTitle => 'Backup and export';

  @override
  String get deviceJoinFailed => 'Join failed';

  @override
  String get deviceJoining => 'Joining';

  @override
  String get deviceName => 'Device name';

  @override
  String get deviceReady => 'Waiting for first report';

  @override
  String get deviceSafeMode => 'Safe mode';

  @override
  String get deviceUnsupported => 'Unsupported device';

  @override
  String get diagBootReason => 'Last start';

  @override
  String get diagFreeHeap => 'Free memory';

  @override
  String get diagLastError => 'Last error code';

  @override
  String get diagRejoins => 'Network rejoins';

  @override
  String get diagResets => 'Restarts';

  @override
  String get diagUptime => 'Running for';

  @override
  String get diagnostics => 'Diagnostics';

  @override
  String get disableUser => 'Disable';

  @override
  String get enableUser => 'Enable';

  @override
  String get userDisabled => 'disabled';

  @override
  String get displayName => 'Display name';

  @override
  String get done => 'Done';

  @override
  String get editConfig => 'Edit configuration';

  @override
  String get errorAlreadySetUp => 'This gateway is already set up.';

  @override
  String get errorConflict => 'That is not possible right now.';

  @override
  String get errorDeviceNotReady => 'The device is not ready yet.';

  @override
  String get errorDeviceSafeMode =>
      'The device is in safe mode and does not water.';

  @override
  String get errorHubTimeout =>
      'The gateway did not answer in time. It may still have worked; check again in a moment.';

  @override
  String get errorHubUnavailable =>
      'The watering service is not reachable right now.';

  @override
  String get errorIncompatibleHub =>
      'The gateway parts do not fit together. Update the gateway.';

  @override
  String get errorInvalidCredentials => 'Wrong username or password.';

  @override
  String get errorInvalidInvite => 'This invite is not valid (anymore).';

  @override
  String get errorInvalidSetupCode => 'The setup code is wrong.';

  @override
  String get errorNetwork => 'Can\'t reach the gateway.';

  @override
  String get errorRateLimited =>
      'Too many attempts. Wait a moment and try again.';

  @override
  String get errorSlotNotActuator => 'That slot is not a pump.';

  @override
  String get eventsTitle => 'Events';

  @override
  String get noEvents => 'No events yet.';

  @override
  String get executionsTitle => 'Recent decisions';

  @override
  String get noExecutions => 'The rule has not decided anything yet.';

  @override
  String get executionWatered => 'Watered';

  @override
  String executionSkipped(String reason) {
    return 'Skipped: $reason';
  }

  @override
  String get skipClock => 'clock not synced';

  @override
  String get skipCooldown => 'too soon after the last watering';

  @override
  String get skipDailyLimit => 'daily limit reached';

  @override
  String get skipNoPump => 'no pump available';

  @override
  String get skipPending => 'a watering is already pending';

  @override
  String get skipQuietHours => 'quiet hours';

  @override
  String get skipSensorError => 'sensor problem';

  @override
  String get exportTitle => 'Export';

  @override
  String get exportBody =>
      'A ZIP file with all plants, devices, readings, commands and users (without passwords). Your password is needed.';

  @override
  String get exportStart => 'Export data';

  @override
  String get exportDone => 'Export downloaded.';

  @override
  String get exportUnsupported =>
      'Downloading is only supported in the web app for now.';

  @override
  String get fastReportHold => 'Keep fast reports after watering';

  @override
  String get fastReportInterval => 'Report interval while watering';

  @override
  String get reportInterval => 'Report interval';

  @override
  String get reportIntervals => 'Reports';

  @override
  String get gatewayApiVersion => 'Web service version';

  @override
  String get gatewayCoordinator => 'Zigbee coordinator';

  @override
  String get gatewayDatabase => 'Database size';

  @override
  String get gatewayHub => 'Watering service';

  @override
  String get gatewayHubVersion => 'Watering service version';

  @override
  String get gatewayServices => 'Services';

  @override
  String get gatewayZigbee => 'Zigbee';

  @override
  String get statusUnknown => 'Unknown';

  @override
  String get installCode => 'Install code (optional)';

  @override
  String get installCodeHint =>
      'From the label on the module. Needed for deployed modules.';

  @override
  String get installation => 'Installation';

  @override
  String get installationName => 'Name of this installation';

  @override
  String get installationSettings => 'Installation settings';

  @override
  String get inviteAs => 'Invite as';

  @override
  String get inviteCreated => 'Invite created';

  @override
  String inviteExpires(String time) {
    return 'valid until $time';
  }

  @override
  String get inviteShownOnce =>
      'Send this link to the person. It is shown only once.';

  @override
  String get invitesTitle => 'Invites';

  @override
  String get noInvites => 'No open invites.';

  @override
  String get revokeInvite => 'Revoke invite';

  @override
  String get joinAccept => 'Create account';

  @override
  String get joinClose => 'Close';

  @override
  String get joinConfigure => 'Name and configure';

  @override
  String joinCountdown(String time) {
    return 'Open for $time';
  }

  @override
  String get joinFailedBody =>
      'The module could not be set up. Remove it, power-cycle the module and try again.';

  @override
  String get joinIdleTitle => 'Add a device';

  @override
  String joinInstallation(String name) {
    return 'Join $name';
  }

  @override
  String get joinInstructions =>
      'Open the join window, then power up the module or hold its button for 3 seconds.';

  @override
  String get joinOpen => 'Open join window';

  @override
  String get joinOpenTitle => 'Waiting for the module…';

  @override
  String get joinRemoveRetry => 'Remove and try again';

  @override
  String joinRole(String role) {
    return 'You were invited as $role.';
  }

  @override
  String get joinTitle => 'Join';

  @override
  String joinUnsupportedBody(String model) {
    return 'This is not a PlantModule ($model). Remove it.';
  }

  @override
  String get stepJoined => 'Joined the network';

  @override
  String get stepInterviewing => 'Interviewing';

  @override
  String get stepConfiguring => 'Configuring';

  @override
  String get stepReady => 'Ready';

  @override
  String get lastSeenLabel => 'Last seen';

  @override
  String lastUsedAgo(String ago) {
    return 'last used $ago';
  }

  @override
  String get neverUsed => 'never used';

  @override
  String get loginSubtitle => 'Sign in to continue';

  @override
  String get username => 'Username';

  @override
  String get password => 'Password';

  @override
  String get passwordHint => 'At least 8 characters';

  @override
  String get signIn => 'Sign in';

  @override
  String get signOut => 'Sign out';

  @override
  String get thisDevice => 'this device';

  @override
  String get thisDeviceName => 'Name of this device';

  @override
  String get thisDeviceHint => 'Shown in the list of your logins';

  @override
  String get moduleEmpty => 'Empty';

  @override
  String get moduleMoisture => 'Moisture sensor';

  @override
  String get modulePump => 'Pump';

  @override
  String get slotModule => 'Module';

  @override
  String get slotPort => 'Port';

  @override
  String portLabel(String port) {
    return 'Port $port';
  }

  @override
  String get myDevices => 'My devices';

  @override
  String get revokeToken => 'Sign this device out';

  @override
  String get noDevicesBody => 'Open the join window and power up a module.';

  @override
  String get noPlantsNoDevices =>
      'Add a device first, then create your plants.';

  @override
  String get noRulesNoPump =>
      'This plant has no pump, so it cannot be watered by a rule.';

  @override
  String get noSlots => 'Nothing is configured yet.';

  @override
  String get notifyFailed => 'When it fails';

  @override
  String get notifySkipped => 'When it cannot decide';

  @override
  String get notifyWatered => 'When it waters';

  @override
  String get ruleNotify => 'Notify';

  @override
  String get outOfRange => 'Out of range';

  @override
  String get pumpActiveHigh => 'Pump switches on with a high signal';

  @override
  String get pumpMaxRun => 'Longest run';

  @override
  String get pumpMinPause => 'Shortest pause between runs';

  @override
  String quietFrom(String time) {
    return 'From $time';
  }

  @override
  String quietTo(String time) {
    return 'Until $time';
  }

  @override
  String get reauthBody => 'Enter your password to continue.';

  @override
  String get reauthTitle => 'Confirm with your password';

  @override
  String get removeDevice => 'Remove device';

  @override
  String removeDeviceBody(String name) {
    return '$name is removed from the network and its plants lose their sensor and pump. History is kept.';
  }

  @override
  String get removeUser => 'Remove user';

  @override
  String removeUserBody(String name) {
    return '$name loses access immediately.';
  }

  @override
  String get renameDevice => 'Rename';

  @override
  String get ruleMaxPerDay => 'At most per day';

  @override
  String ruleMaxPerDayValue(int count) {
    return 'at most $count a day';
  }

  @override
  String get ruleQuietHours => 'Quiet hours';

  @override
  String ruleQuietValue(String from, String to) {
    return 'quiet $from – $to';
  }

  @override
  String safeModeBody(String reason) {
    return 'The module stopped itself ($reason) and does not water until it is reset.';
  }

  @override
  String get safeModeTitle => 'Safe mode';

  @override
  String get saved => 'Saved.';

  @override
  String get setupCode => 'Setup code';

  @override
  String get setupCodeHint =>
      'Shown in the log of the web service: docker compose logs api';

  @override
  String get setupCreate => 'Set up this gateway';

  @override
  String get setupNeedsHub =>
      'The watering service is not running yet. Setup needs it.';

  @override
  String get setupSubtitle =>
      'Create the owner account. This is only needed once.';

  @override
  String get setupTitle => 'Set up this gateway';

  @override
  String get telegramChat => 'Chat id';

  @override
  String get telegramConfigured => 'Telegram is set up.';

  @override
  String get telegramNotConfigured => 'Telegram is not set up.';

  @override
  String get telegramTitle => 'Telegram';

  @override
  String get telegramToken => 'Bot token';

  @override
  String get telegramTokenHint => 'Leave empty to keep the saved token';

  @override
  String get timezoneHint => 'For example Europe/Berlin';

  @override
  String get transferOwnership => 'Make owner';

  @override
  String transferOwnershipBody(String name) {
    return '$name becomes the owner. You become an admin.';
  }

  @override
  String get usersTitle => 'Users';

  @override
  String get waterQueuedDeviceOffline =>
      'Watering queued. The device is offline and gets it when it is back.';

  @override
  String get noReadings => 'No readings in this period yet.';

  @override
  String get batteryTitle => 'Battery';

  @override
  String get batteryStateOk => 'OK';

  @override
  String get batteryStateLow => 'Low';

  @override
  String get batteryStateCritical => 'Critical';

  @override
  String get batteryStateAbsent => 'No battery';

  @override
  String batteryPercent(int percent) {
    return 'about $percent %';
  }

  @override
  String batteryVolts(String volts) {
    return '$volts V';
  }

  @override
  String get batteryChargingHint => 'Charging cannot be detected.';

  @override
  String batteryCalibrated(String delta) {
    return 'Calibrated ($delta)';
  }

  @override
  String get calibrateBattery => 'Calibrate battery';

  @override
  String calibrateBatteryBody(String volts) {
    return 'Measure the cell with a multimeter and enter the value. The module reports $volts V now. Values more than 10 % off are refused.';
  }

  @override
  String get measuredVolts => 'Measured voltage';

  @override
  String get calibrate => 'Calibrate';

  @override
  String get batteryCalibrationSent => 'Calibration sent to the device.';

  @override
  String get batteryNoData => 'No battery readings yet.';

  @override
  String get batteryCriticalThreshold => 'Battery critical (mV)';

  @override
  String get batteryThresholdsHint =>
      'Applied to all devices as soon as they confirm it.';

  @override
  String get batteryThresholdsInvalid =>
      'Critical must be below low, both between 3000 and 4000 mV.';

  @override
  String get batteryCell => 'Li-ion / LiPo, one cell';

  @override
  String alertBatteryCritical(String subject) {
    return '$subject: battery critical';
  }

  @override
  String get commandFailedBattery => 'Battery too low to water';

  @override
  String get waterBatteryHint =>
      'This module\'s battery is critical: it will refuse to water.';

  @override
  String get batteryVoltage => 'Voltage';

  @override
  String get batteryLevel => 'Level (estimate)';

  @override
  String get showMeasured => 'Show measured values';

  @override
  String get showPercent => 'Show percent';

  @override
  String moistureRawSemantics(int value) {
    return 'Measured value $value';
  }

  @override
  String chartSummaryRaw(int min, int max) {
    return 'Measured value between $min and $max in this period';
  }

  @override
  String measuredAs(int value) {
    return 'Measured value $value';
  }

  @override
  String calibratedAs(int percent) {
    return 'Calibrated: $percent %';
  }

  @override
  String get plantMenu => 'Plant menu';

  @override
  String get readNow => 'Read now';

  @override
  String get readingRequested =>
      'Reading requested. It arrives in a few seconds.';
}
