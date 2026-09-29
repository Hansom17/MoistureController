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
  String get switchHousehold => 'Switch household';

  @override
  String get roleViewer => 'Viewer';

  @override
  String get roleMember => 'Member';

  @override
  String get roleAdmin => 'Admin';

  @override
  String get roleOwner => 'Owner';

  @override
  String hubOfflineBanner(String time) {
    return 'Hub offline since $time. Watering is delivered when it\'s back.';
  }

  @override
  String get noPlantsTitle => 'Start with your first plant';

  @override
  String get noPlantsBody => 'Add a device to start measuring moisture.';

  @override
  String get noHouseholdTitle => 'Create your first household';

  @override
  String get noHouseholdBody => 'Or join one with an invite link.';

  @override
  String get retry => 'Retry';

  @override
  String get errorGeneric => 'Something went wrong.';

  @override
  String get errorForbidden => 'Your role no longer allows this.';

  @override
  String get errorSafetyLimit => 'That\'s longer than this pump\'s limit.';

  @override
  String get errorHubOffline => 'The hub is offline.';

  @override
  String get errorTooLate => 'The device already picked this up.';

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
  String get deviceSleeping => 'Sleeping';

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
  String batteryValue(int percent) {
    return 'Battery $percent %';
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
      'Devices sleep between readings. Watering starts on the next wake.';

  @override
  String pumpLimit(int seconds) {
    return 'Pump limit: $seconds s';
  }

  @override
  String get waterQueued => 'Watering queued';

  @override
  String get waterQueuedHubOffline =>
      'Queued. It\'s delivered when the hub is back online.';

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
  String commandQueued(String time) {
    return 'Queued · device expected ~$time';
  }

  @override
  String get commandDelivered => 'Delivered';

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
  String get originCloudRule => 'Rule (cloud)';

  @override
  String get originHubRule => 'Rule (hub)';

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
  String get deleteRule => 'Delete rule';

  @override
  String ruleSummary(int percent, int seconds, int hours) {
    return 'Below $percent % → water $seconds s, at most every $hours h';
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
  String signalValue(int rssi) {
    return 'Signal $rssi dBm';
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
  String get wakeInterval => 'Wake interval';

  @override
  String everyMinutes(int minutes) {
    return 'every $minutes min';
  }

  @override
  String get nextExpected => 'Next wake expected';

  @override
  String get slots => 'Slots';

  @override
  String slotLabel(int index) {
    return 'Slot $index';
  }

  @override
  String pinLabel(int pin) {
    return 'GPIO $pin';
  }

  @override
  String get identify => 'Identify';

  @override
  String get reboot => 'Reboot';

  @override
  String get serviceMode => 'Service mode';

  @override
  String get deviceActionSent => 'Sent. The device acts on its next wake.';

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
  String get household => 'Household';

  @override
  String get timezone => 'Time zone';

  @override
  String get yourRole => 'Your role';

  @override
  String get demoSection => 'Demo';

  @override
  String get demoRole => 'Demo role in this household';

  @override
  String get demoRoleHint => 'Only in the dev build without a backend.';

  @override
  String get notAllowed => 'Your role doesn\'t allow this.';

  @override
  String get battery => 'Battery';

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
  String get hubTitle => 'Hub';

  @override
  String get hubNoneTitle => 'Keep watering without internet';

  @override
  String get hubNoneBody =>
      'A hub is a small computer at home, like a Raspberry Pi, that runs your watering rules locally. Start the hub software, then enter the code it shows.';

  @override
  String get hubAdd => 'Add hub';

  @override
  String get hubCodeLabel => 'Code shown by the hub';

  @override
  String get hubCodeInvalid => 'Enter the 8-character code, like K7QM-2XPA.';

  @override
  String get hubClaimNote =>
      'After adding a hub, re-pair every device of this household to it.';

  @override
  String get hubAdded => 'Hub added. Waiting for it to connect.';

  @override
  String get hubEnrolling => 'Waiting for the hub to connect';

  @override
  String hubOfflineSince(String time) {
    return 'Offline since $time';
  }

  @override
  String get hubInSync => 'Settings in sync';

  @override
  String get hubSyncing => 'Syncing settings';

  @override
  String get hubAgentVersion => 'Agent version';

  @override
  String hubUpdateAvailable(String version) {
    return 'Update available: $version';
  }

  @override
  String get hubUpdateHint =>
      'On the hub, run: docker compose pull && docker compose up -d';

  @override
  String get hubQueue => 'Messages waiting for the cloud';

  @override
  String get hubClock => 'Clock';

  @override
  String get hubClockOk => 'Synced';

  @override
  String get hubClockBad => 'Not synced: no automatic watering';

  @override
  String get hubLastReport => 'Last report';

  @override
  String get hubLanAddress => 'LAN address';

  @override
  String get hubLanHint =>
      'Devices connect to this address. Override it if the hub has several network interfaces.';

  @override
  String get hubLanReported => 'Reported by the hub';

  @override
  String get hubLanOverridden => 'Set manually';

  @override
  String get hubLanUnknown => 'Not reported yet';

  @override
  String get hubLanReset => 'Use reported address';

  @override
  String get edit => 'Edit';

  @override
  String get hubRepairTitle => 'Devices to re-pair';

  @override
  String get hubRepairBody =>
      'These devices still use the old connection. Re-pair each one with the phone app, close to the device.';

  @override
  String get deviceNeedsRepair => 'Needs re-pairing';

  @override
  String get hubRemove => 'Remove hub';

  @override
  String get hubRemoveTitle => 'Remove the hub?';

  @override
  String get hubRemoveBody =>
      'All devices of this household stop reporting until you re-pair them to the cloud. History is kept.';

  @override
  String get hubRemoved => 'Hub removed';

  @override
  String get hubNone => 'No hub';

  @override
  String get errorInvalidCode =>
      'That code isn\'t valid or has expired. The hub shows a new one.';

  @override
  String get errorHubExists => 'This household already has a hub.';

  @override
  String get errorReauth => 'Sign in again to do this.';
}
