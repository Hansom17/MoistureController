import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:intl/intl.dart' as intl;

import 'app_localizations_de.dart';
import 'app_localizations_en.dart';

// ignore_for_file: type=lint

/// Callers can lookup localized strings with an instance of AppLocalizations
/// returned by `AppLocalizations.of(context)`.
///
/// Applications need to include `AppLocalizations.delegate()` in their app's
/// `localizationDelegates` list, and the locales they support in the app's
/// `supportedLocales` list. For example:
///
/// ```dart
/// import 'l10n/app_localizations.dart';
///
/// return MaterialApp(
///   localizationsDelegates: AppLocalizations.localizationsDelegates,
///   supportedLocales: AppLocalizations.supportedLocales,
///   home: MyApplicationHome(),
/// );
/// ```
///
/// ## Update pubspec.yaml
///
/// Please make sure to update your pubspec.yaml to include the following
/// packages:
///
/// ```yaml
/// dependencies:
///   # Internationalization support.
///   flutter_localizations:
///     sdk: flutter
///   intl: any # Use the pinned version from flutter_localizations
///
///   # Rest of dependencies
/// ```
///
/// ## iOS Applications
///
/// iOS applications define key application metadata, including supported
/// locales, in an Info.plist file that is built into the application bundle.
/// To configure the locales supported by your app, you’ll need to edit this
/// file.
///
/// First, open your project’s ios/Runner.xcworkspace Xcode workspace file.
/// Then, in the Project Navigator, open the Info.plist file under the Runner
/// project’s Runner folder.
///
/// Next, select the Information Property List item, select Add Item from the
/// Editor menu, then select Localizations from the pop-up menu.
///
/// Select and expand the newly-created Localizations item then, for each
/// locale your application supports, add a new item and select the locale
/// you wish to add from the pop-up menu in the Value field. This list should
/// be consistent with the languages listed in the AppLocalizations.supportedLocales
/// property.
abstract class AppLocalizations {
  AppLocalizations(String locale)
    : localeName = intl.Intl.canonicalizedLocale(locale.toString());

  final String localeName;

  static AppLocalizations of(BuildContext context) {
    return Localizations.of<AppLocalizations>(context, AppLocalizations)!;
  }

  static const LocalizationsDelegate<AppLocalizations> delegate =
      _AppLocalizationsDelegate();

  /// A list of this localizations delegate along with the default localizations
  /// delegates.
  ///
  /// Returns a list of localizations delegates containing this delegate along with
  /// GlobalMaterialLocalizations.delegate, GlobalCupertinoLocalizations.delegate,
  /// and GlobalWidgetsLocalizations.delegate.
  ///
  /// Additional delegates can be added by appending to this list in
  /// MaterialApp. This list does not have to be used at all if a custom list
  /// of delegates is preferred or required.
  static const List<LocalizationsDelegate<dynamic>> localizationsDelegates =
      <LocalizationsDelegate<dynamic>>[
        delegate,
        GlobalMaterialLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
      ];

  /// A list of this localizations delegate's supported locales.
  static const List<Locale> supportedLocales = <Locale>[
    Locale('de'),
    Locale('en'),
  ];

  /// No description provided for @appTitle.
  ///
  /// In en, this message translates to:
  /// **'Moisture'**
  String get appTitle;

  /// No description provided for @navPlants.
  ///
  /// In en, this message translates to:
  /// **'Plants'**
  String get navPlants;

  /// No description provided for @navDevices.
  ///
  /// In en, this message translates to:
  /// **'Devices'**
  String get navDevices;

  /// No description provided for @navAlerts.
  ///
  /// In en, this message translates to:
  /// **'Alerts'**
  String get navAlerts;

  /// No description provided for @navSettings.
  ///
  /// In en, this message translates to:
  /// **'Settings'**
  String get navSettings;

  /// No description provided for @roleViewer.
  ///
  /// In en, this message translates to:
  /// **'Viewer'**
  String get roleViewer;

  /// No description provided for @roleMember.
  ///
  /// In en, this message translates to:
  /// **'Member'**
  String get roleMember;

  /// No description provided for @roleAdmin.
  ///
  /// In en, this message translates to:
  /// **'Admin'**
  String get roleAdmin;

  /// No description provided for @roleOwner.
  ///
  /// In en, this message translates to:
  /// **'Owner'**
  String get roleOwner;

  /// No description provided for @noPlantsTitle.
  ///
  /// In en, this message translates to:
  /// **'Start with your first plant'**
  String get noPlantsTitle;

  /// No description provided for @retry.
  ///
  /// In en, this message translates to:
  /// **'Retry'**
  String get retry;

  /// No description provided for @errorGeneric.
  ///
  /// In en, this message translates to:
  /// **'Something went wrong.'**
  String get errorGeneric;

  /// No description provided for @errorForbidden.
  ///
  /// In en, this message translates to:
  /// **'Your role no longer allows this.'**
  String get errorForbidden;

  /// No description provided for @errorSafetyLimit.
  ///
  /// In en, this message translates to:
  /// **'That\'s longer than this pump\'s limit.'**
  String get errorSafetyLimit;

  /// No description provided for @errorBusy.
  ///
  /// In en, this message translates to:
  /// **'The device is busy. Try again shortly.'**
  String get errorBusy;

  /// No description provided for @moistureSemantics.
  ///
  /// In en, this message translates to:
  /// **'Moisture {percent} percent'**
  String moistureSemantics(int percent);

  /// No description provided for @percentValue.
  ///
  /// In en, this message translates to:
  /// **'{value} %'**
  String percentValue(int value);

  /// No description provided for @secondsValue.
  ///
  /// In en, this message translates to:
  /// **'{value} s'**
  String secondsValue(int value);

  /// No description provided for @hoursValue.
  ///
  /// In en, this message translates to:
  /// **'{value} h'**
  String hoursValue(int value);

  /// No description provided for @justNow.
  ///
  /// In en, this message translates to:
  /// **'just now'**
  String get justNow;

  /// No description provided for @minutesAgo.
  ///
  /// In en, this message translates to:
  /// **'{n} min ago'**
  String minutesAgo(int n);

  /// No description provided for @hoursAgo.
  ///
  /// In en, this message translates to:
  /// **'{n} h ago'**
  String hoursAgo(int n);

  /// No description provided for @daysAgo.
  ///
  /// In en, this message translates to:
  /// **'{n} d ago'**
  String daysAgo(int n);

  /// No description provided for @deviceOnline.
  ///
  /// In en, this message translates to:
  /// **'Online'**
  String get deviceOnline;

  /// No description provided for @deviceLate.
  ///
  /// In en, this message translates to:
  /// **'Late'**
  String get deviceLate;

  /// No description provided for @deviceOffline.
  ///
  /// In en, this message translates to:
  /// **'Offline'**
  String get deviceOffline;

  /// No description provided for @lastSeen.
  ///
  /// In en, this message translates to:
  /// **'last seen {ago}'**
  String lastSeen(String ago);

  /// No description provided for @lastReading.
  ///
  /// In en, this message translates to:
  /// **'Last reading {ago}'**
  String lastReading(String ago);

  /// No description provided for @trendFalling.
  ///
  /// In en, this message translates to:
  /// **'Drying'**
  String get trendFalling;

  /// No description provided for @trendSteady.
  ///
  /// In en, this message translates to:
  /// **'Steady'**
  String get trendSteady;

  /// No description provided for @trendRising.
  ///
  /// In en, this message translates to:
  /// **'Rising'**
  String get trendRising;

  /// No description provided for @pendingCommand.
  ///
  /// In en, this message translates to:
  /// **'Watering pending'**
  String get pendingCommand;

  /// No description provided for @waterNow.
  ///
  /// In en, this message translates to:
  /// **'Water now'**
  String get waterNow;

  /// No description provided for @waterFor.
  ///
  /// In en, this message translates to:
  /// **'Water for {seconds} s'**
  String waterFor(int seconds);

  /// No description provided for @waterSheetTitle.
  ///
  /// In en, this message translates to:
  /// **'Water {plant}'**
  String waterSheetTitle(String plant);

  /// No description provided for @waterSheetHint.
  ///
  /// In en, this message translates to:
  /// **'Watering starts as soon as the module confirms. If it is offline, it is sent when it is back.'**
  String get waterSheetHint;

  /// No description provided for @pumpLimit.
  ///
  /// In en, this message translates to:
  /// **'Pump limit: {seconds} s'**
  String pumpLimit(int seconds);

  /// No description provided for @waterQueued.
  ///
  /// In en, this message translates to:
  /// **'Watering queued'**
  String get waterQueued;

  /// No description provided for @cancel.
  ///
  /// In en, this message translates to:
  /// **'Cancel'**
  String get cancel;

  /// No description provided for @cancelCommand.
  ///
  /// In en, this message translates to:
  /// **'Cancel watering'**
  String get cancelCommand;

  /// No description provided for @cancelCommandHint.
  ///
  /// In en, this message translates to:
  /// **'Best effort — it may already have run.'**
  String get cancelCommandHint;

  /// No description provided for @commandTitle.
  ///
  /// In en, this message translates to:
  /// **'{seconds} s watering'**
  String commandTitle(int seconds);

  /// No description provided for @commandRunning.
  ///
  /// In en, this message translates to:
  /// **'Running until {time}'**
  String commandRunning(String time);

  /// No description provided for @commandDone.
  ///
  /// In en, this message translates to:
  /// **'Done'**
  String get commandDone;

  /// No description provided for @commandFailed.
  ///
  /// In en, this message translates to:
  /// **'Failed'**
  String get commandFailed;

  /// No description provided for @commandExpired.
  ///
  /// In en, this message translates to:
  /// **'Expired'**
  String get commandExpired;

  /// No description provided for @commandCancelled.
  ///
  /// In en, this message translates to:
  /// **'Cancelled'**
  String get commandCancelled;

  /// No description provided for @originUser.
  ///
  /// In en, this message translates to:
  /// **'Manual'**
  String get originUser;

  /// No description provided for @originRule.
  ///
  /// In en, this message translates to:
  /// **'Rule'**
  String get originRule;

  /// No description provided for @historyTitle.
  ///
  /// In en, this message translates to:
  /// **'Moisture history'**
  String get historyTitle;

  /// No description provided for @range24h.
  ///
  /// In en, this message translates to:
  /// **'24 h'**
  String get range24h;

  /// No description provided for @range7d.
  ///
  /// In en, this message translates to:
  /// **'7 d'**
  String get range7d;

  /// No description provided for @range30d.
  ///
  /// In en, this message translates to:
  /// **'30 d'**
  String get range30d;

  /// No description provided for @range1y.
  ///
  /// In en, this message translates to:
  /// **'1 y'**
  String get range1y;

  /// No description provided for @chartSummary.
  ///
  /// In en, this message translates to:
  /// **'Moisture between {min} and {max} % in this period'**
  String chartSummary(int min, int max);

  /// No description provided for @commandsTitle.
  ///
  /// In en, this message translates to:
  /// **'Watering'**
  String get commandsTitle;

  /// No description provided for @noCommands.
  ///
  /// In en, this message translates to:
  /// **'No watering yet.'**
  String get noCommands;

  /// No description provided for @rulesTitle.
  ///
  /// In en, this message translates to:
  /// **'Rules'**
  String get rulesTitle;

  /// No description provided for @noRules.
  ///
  /// In en, this message translates to:
  /// **'Add a rule to water automatically.'**
  String get noRules;

  /// No description provided for @addRule.
  ///
  /// In en, this message translates to:
  /// **'Add rule'**
  String get addRule;

  /// No description provided for @editRule.
  ///
  /// In en, this message translates to:
  /// **'Edit rule'**
  String get editRule;

  /// No description provided for @ruleSummary.
  ///
  /// In en, this message translates to:
  /// **'Below {percent} %: water {seconds} s, at most every {hours} h'**
  String ruleSummary(int percent, int seconds, int hours);

  /// No description provided for @ruleBelow.
  ///
  /// In en, this message translates to:
  /// **'Water when moisture is below'**
  String get ruleBelow;

  /// No description provided for @ruleDuration.
  ///
  /// In en, this message translates to:
  /// **'Watering duration'**
  String get ruleDuration;

  /// No description provided for @ruleInterval.
  ///
  /// In en, this message translates to:
  /// **'At most every'**
  String get ruleInterval;

  /// No description provided for @ruleEnabled.
  ///
  /// In en, this message translates to:
  /// **'Rule enabled'**
  String get ruleEnabled;

  /// No description provided for @save.
  ///
  /// In en, this message translates to:
  /// **'Save'**
  String get save;

  /// No description provided for @delete.
  ///
  /// In en, this message translates to:
  /// **'Delete'**
  String get delete;

  /// No description provided for @noDevices.
  ///
  /// In en, this message translates to:
  /// **'Add your first device'**
  String get noDevices;

  /// No description provided for @firmwareValue.
  ///
  /// In en, this message translates to:
  /// **'Firmware {version}'**
  String firmwareValue(String version);

  /// No description provided for @configInSync.
  ///
  /// In en, this message translates to:
  /// **'Config in sync'**
  String get configInSync;

  /// No description provided for @configPending.
  ///
  /// In en, this message translates to:
  /// **'Config pending (rev {rev})'**
  String configPending(int rev);

  /// No description provided for @configRejected.
  ///
  /// In en, this message translates to:
  /// **'Config rejected'**
  String get configRejected;

  /// No description provided for @deviceDetails.
  ///
  /// In en, this message translates to:
  /// **'Details'**
  String get deviceDetails;

  /// No description provided for @board.
  ///
  /// In en, this message translates to:
  /// **'Board'**
  String get board;

  /// No description provided for @slots.
  ///
  /// In en, this message translates to:
  /// **'Slots'**
  String get slots;

  /// No description provided for @slotLabel.
  ///
  /// In en, this message translates to:
  /// **'Slot {index}'**
  String slotLabel(int index);

  /// No description provided for @identify.
  ///
  /// In en, this message translates to:
  /// **'Identify'**
  String get identify;

  /// No description provided for @reboot.
  ///
  /// In en, this message translates to:
  /// **'Reboot'**
  String get reboot;

  /// No description provided for @deviceActionSent.
  ///
  /// In en, this message translates to:
  /// **'Sent to the device.'**
  String get deviceActionSent;

  /// No description provided for @openAlerts.
  ///
  /// In en, this message translates to:
  /// **'Open'**
  String get openAlerts;

  /// No description provided for @closedAlerts.
  ///
  /// In en, this message translates to:
  /// **'Closed'**
  String get closedAlerts;

  /// No description provided for @noAlerts.
  ///
  /// In en, this message translates to:
  /// **'All plants are fine'**
  String get noAlerts;

  /// No description provided for @alertDeviceOffline.
  ///
  /// In en, this message translates to:
  /// **'{subject} is offline'**
  String alertDeviceOffline(String subject);

  /// No description provided for @alertBatteryLow.
  ///
  /// In en, this message translates to:
  /// **'{subject}: battery low'**
  String alertBatteryLow(String subject);

  /// No description provided for @alertSensorSuspect.
  ///
  /// In en, this message translates to:
  /// **'{subject}: sensor readings look wrong'**
  String alertSensorSuspect(String subject);

  /// No description provided for @alertCommandFailed.
  ///
  /// In en, this message translates to:
  /// **'{subject}: watering failed'**
  String alertCommandFailed(String subject);

  /// No description provided for @acknowledge.
  ///
  /// In en, this message translates to:
  /// **'Acknowledge'**
  String get acknowledge;

  /// No description provided for @acknowledgedAgo.
  ///
  /// In en, this message translates to:
  /// **'Acknowledged {ago}'**
  String acknowledgedAgo(String ago);

  /// No description provided for @appearance.
  ///
  /// In en, this message translates to:
  /// **'Appearance'**
  String get appearance;

  /// No description provided for @themeSystem.
  ///
  /// In en, this message translates to:
  /// **'System'**
  String get themeSystem;

  /// No description provided for @themeLight.
  ///
  /// In en, this message translates to:
  /// **'Light'**
  String get themeLight;

  /// No description provided for @themeDark.
  ///
  /// In en, this message translates to:
  /// **'Dark'**
  String get themeDark;

  /// No description provided for @language.
  ///
  /// In en, this message translates to:
  /// **'Language'**
  String get language;

  /// No description provided for @timezone.
  ///
  /// In en, this message translates to:
  /// **'Time zone'**
  String get timezone;

  /// No description provided for @demoSection.
  ///
  /// In en, this message translates to:
  /// **'Demo'**
  String get demoSection;

  /// No description provided for @demoRole.
  ///
  /// In en, this message translates to:
  /// **'Demo role in this household'**
  String get demoRole;

  /// No description provided for @demoRoleHint.
  ///
  /// In en, this message translates to:
  /// **'Only in the dev build without a backend.'**
  String get demoRoleHint;

  /// No description provided for @notAllowed.
  ///
  /// In en, this message translates to:
  /// **'Your role doesn\'t allow this.'**
  String get notAllowed;

  /// No description provided for @signal.
  ///
  /// In en, this message translates to:
  /// **'Signal'**
  String get signal;

  /// No description provided for @firmware.
  ///
  /// In en, this message translates to:
  /// **'Firmware'**
  String get firmware;

  /// No description provided for @noReading.
  ///
  /// In en, this message translates to:
  /// **'No reading yet'**
  String get noReading;

  /// No description provided for @alertOther.
  ///
  /// In en, this message translates to:
  /// **'{subject}: {kind}'**
  String alertOther(String subject, String kind);

  /// No description provided for @gatewayClock.
  ///
  /// In en, this message translates to:
  /// **'Clock'**
  String get gatewayClock;

  /// No description provided for @gatewayClockOk.
  ///
  /// In en, this message translates to:
  /// **'Synced'**
  String get gatewayClockOk;

  /// No description provided for @gatewayClockBad.
  ///
  /// In en, this message translates to:
  /// **'Not synced: no automatic watering'**
  String get gatewayClockBad;

  /// No description provided for @errorReauth.
  ///
  /// In en, this message translates to:
  /// **'Sign in again to do this.'**
  String get errorReauth;

  /// No description provided for @serverTitle.
  ///
  /// In en, this message translates to:
  /// **'Server'**
  String get serverTitle;

  /// No description provided for @connSearching.
  ///
  /// In en, this message translates to:
  /// **'Looking for the server on your network …'**
  String get connSearching;

  /// No description provided for @connUnreachable.
  ///
  /// In en, this message translates to:
  /// **'Can\'t reach the server.'**
  String get connUnreachable;

  /// No description provided for @connChoose.
  ///
  /// In en, this message translates to:
  /// **'Several servers found. Choose one.'**
  String get connChoose;

  /// No description provided for @connEnterAddress.
  ///
  /// In en, this message translates to:
  /// **'Enter address'**
  String get connEnterAddress;

  /// No description provided for @serverCurrent.
  ///
  /// In en, this message translates to:
  /// **'Connected to'**
  String get serverCurrent;

  /// No description provided for @serverFound.
  ///
  /// In en, this message translates to:
  /// **'Servers on your network'**
  String get serverFound;

  /// No description provided for @serverSearchAgain.
  ///
  /// In en, this message translates to:
  /// **'Search again'**
  String get serverSearchAgain;

  /// No description provided for @serverAddress.
  ///
  /// In en, this message translates to:
  /// **'Server address'**
  String get serverAddress;

  /// No description provided for @serverAddressHint.
  ///
  /// In en, this message translates to:
  /// **'192.168.1.10:8000'**
  String get serverAddressHint;

  /// No description provided for @serverAddressInvalid.
  ///
  /// In en, this message translates to:
  /// **'That is not a valid address.'**
  String get serverAddressInvalid;

  /// No description provided for @serverAddressNotLocal.
  ///
  /// In en, this message translates to:
  /// **'Only addresses on your home network are allowed.'**
  String get serverAddressNotLocal;

  /// No description provided for @serverAddressNoAnswer.
  ///
  /// In en, this message translates to:
  /// **'No Moisture server answers there.'**
  String get serverAddressNoAnswer;

  /// No description provided for @serverAuthDev.
  ///
  /// In en, this message translates to:
  /// **'Dev login (no password)'**
  String get serverAuthDev;

  /// No description provided for @serverAuthFirebase.
  ///
  /// In en, this message translates to:
  /// **'Firebase login'**
  String get serverAuthFirebase;

  /// No description provided for @serverDevWarningTitle.
  ///
  /// In en, this message translates to:
  /// **'Unsigned dev login'**
  String get serverDevWarningTitle;

  /// No description provided for @serverDevWarningBody.
  ///
  /// In en, this message translates to:
  /// **'This server accepts logins without a password. Only continue if it is your own development server.'**
  String get serverDevWarningBody;

  /// No description provided for @serverContinue.
  ///
  /// In en, this message translates to:
  /// **'Connect'**
  String get serverContinue;

  /// No description provided for @serverUseThis.
  ///
  /// In en, this message translates to:
  /// **'Use this server'**
  String get serverUseThis;

  /// No description provided for @commandQueued.
  ///
  /// In en, this message translates to:
  /// **'Queued'**
  String get commandQueued;

  /// No description provided for @signalValue.
  ///
  /// In en, this message translates to:
  /// **'Link quality {quality}'**
  String signalValue(int quality);

  /// No description provided for @noPlantsBody.
  ///
  /// In en, this message translates to:
  /// **'Create a plant for a sensor of one of your devices.'**
  String get noPlantsBody;

  /// No description provided for @serverSubtitle.
  ///
  /// In en, this message translates to:
  /// **'The gateway this app talks to'**
  String get serverSubtitle;

  /// No description provided for @gatewayTitle.
  ///
  /// In en, this message translates to:
  /// **'Gateway'**
  String get gatewayTitle;

  /// No description provided for @commandDelivered.
  ///
  /// In en, this message translates to:
  /// **'Running'**
  String get commandDelivered;

  /// No description provided for @account.
  ///
  /// In en, this message translates to:
  /// **'Account'**
  String get account;

  /// No description provided for @addDevice.
  ///
  /// In en, this message translates to:
  /// **'Add device'**
  String get addDevice;

  /// No description provided for @addPlant.
  ///
  /// In en, this message translates to:
  /// **'Add plant'**
  String get addPlant;

  /// No description provided for @editPlant.
  ///
  /// In en, this message translates to:
  /// **'Edit plant'**
  String get editPlant;

  /// No description provided for @plantName.
  ///
  /// In en, this message translates to:
  /// **'Name'**
  String get plantName;

  /// No description provided for @plantSensor.
  ///
  /// In en, this message translates to:
  /// **'Moisture sensor'**
  String get plantSensor;

  /// No description provided for @plantPump.
  ///
  /// In en, this message translates to:
  /// **'Pump'**
  String get plantPump;

  /// No description provided for @plantNoSlots.
  ///
  /// In en, this message translates to:
  /// **'No device has a sensor or pump configured yet. Set up a device first.'**
  String get plantNoSlots;

  /// No description provided for @alertSafeMode.
  ///
  /// In en, this message translates to:
  /// **'{subject} is in safe mode'**
  String alertSafeMode(String subject);

  /// No description provided for @alertZigbeeOffline.
  ///
  /// In en, this message translates to:
  /// **'Zigbee is not running'**
  String get alertZigbeeOffline;

  /// No description provided for @auditTitle.
  ///
  /// In en, this message translates to:
  /// **'Activity'**
  String get auditTitle;

  /// No description provided for @noAudit.
  ///
  /// In en, this message translates to:
  /// **'Nothing yet.'**
  String get noAudit;

  /// No description provided for @backupTitle.
  ///
  /// In en, this message translates to:
  /// **'Backup'**
  String get backupTitle;

  /// No description provided for @backupBody.
  ///
  /// In en, this message translates to:
  /// **'Makes a consistent copy of the gateway databases on the gateway. The Zigbee network data has to be copied separately (scripts/backup.sh).'**
  String get backupBody;

  /// No description provided for @backupNow.
  ///
  /// In en, this message translates to:
  /// **'Back up now'**
  String get backupNow;

  /// No description provided for @backupDone.
  ///
  /// In en, this message translates to:
  /// **'Backup written on the gateway.'**
  String get backupDone;

  /// No description provided for @bannerHubDown.
  ///
  /// In en, this message translates to:
  /// **'The watering service is not reachable. You see the last known data; changes are not possible.'**
  String get bannerHubDown;

  /// No description provided for @bannerZigbeeDown.
  ///
  /// In en, this message translates to:
  /// **'Zigbee is not running. Data and commands are paused.'**
  String get bannerZigbeeDown;

  /// No description provided for @batteryThreshold.
  ///
  /// In en, this message translates to:
  /// **'Low battery warning below'**
  String get batteryThreshold;

  /// No description provided for @calDry.
  ///
  /// In en, this message translates to:
  /// **'Dry value (raw)'**
  String get calDry;

  /// No description provided for @calWet.
  ///
  /// In en, this message translates to:
  /// **'Wet value (raw)'**
  String get calWet;

  /// No description provided for @changePassword.
  ///
  /// In en, this message translates to:
  /// **'Change password'**
  String get changePassword;

  /// No description provided for @currentPassword.
  ///
  /// In en, this message translates to:
  /// **'Current password'**
  String get currentPassword;

  /// No description provided for @newPassword.
  ///
  /// In en, this message translates to:
  /// **'New password'**
  String get newPassword;

  /// No description provided for @passwordChangeHint.
  ///
  /// In en, this message translates to:
  /// **'Changing it signs out your other devices.'**
  String get passwordChangeHint;

  /// No description provided for @passwordChanged.
  ///
  /// In en, this message translates to:
  /// **'Password changed.'**
  String get passwordChanged;

  /// No description provided for @changeRole.
  ///
  /// In en, this message translates to:
  /// **'Change role'**
  String get changeRole;

  /// No description provided for @channelApp.
  ///
  /// In en, this message translates to:
  /// **'In the app'**
  String get channelApp;

  /// No description provided for @channelTelegram.
  ///
  /// In en, this message translates to:
  /// **'Telegram'**
  String get channelTelegram;

  /// No description provided for @clearSafeMode.
  ///
  /// In en, this message translates to:
  /// **'Clear safe mode'**
  String get clearSafeMode;

  /// No description provided for @commandQueuedOffline.
  ///
  /// In en, this message translates to:
  /// **'Queued · device offline'**
  String get commandQueuedOffline;

  /// No description provided for @configApplyNote.
  ///
  /// In en, this message translates to:
  /// **'The change is applied as soon as the device confirms it.'**
  String get configApplyNote;

  /// No description provided for @configConflict.
  ///
  /// In en, this message translates to:
  /// **'Someone else changed this device meanwhile. The current configuration was loaded; please check and save again.'**
  String get configConflict;

  /// No description provided for @configNoBoard.
  ///
  /// In en, this message translates to:
  /// **'This device has not reported its board yet.'**
  String get configNoBoard;

  /// No description provided for @configPendingBody.
  ///
  /// In en, this message translates to:
  /// **'Revision {rev} is waiting for the device to confirm it.'**
  String configPendingBody(int rev);

  /// No description provided for @configRejectedBody.
  ///
  /// In en, this message translates to:
  /// **'The device rejected the configuration: {error}'**
  String configRejectedBody(String error);

  /// No description provided for @configRevert.
  ///
  /// In en, this message translates to:
  /// **'Use the running configuration'**
  String get configRevert;

  /// No description provided for @configRevision.
  ///
  /// In en, this message translates to:
  /// **'Configuration (running / sent)'**
  String get configRevision;

  /// No description provided for @configSaved.
  ///
  /// In en, this message translates to:
  /// **'Configuration sent to the device.'**
  String get configSaved;

  /// No description provided for @confirm.
  ///
  /// In en, this message translates to:
  /// **'Confirm'**
  String get confirm;

  /// No description provided for @copied.
  ///
  /// In en, this message translates to:
  /// **'Copied.'**
  String get copied;

  /// No description provided for @copyLink.
  ///
  /// In en, this message translates to:
  /// **'Copy link'**
  String get copyLink;

  /// No description provided for @createInvite.
  ///
  /// In en, this message translates to:
  /// **'Create invite'**
  String get createInvite;

  /// No description provided for @dataTitle.
  ///
  /// In en, this message translates to:
  /// **'Backup and export'**
  String get dataTitle;

  /// No description provided for @deviceJoinFailed.
  ///
  /// In en, this message translates to:
  /// **'Join failed'**
  String get deviceJoinFailed;

  /// No description provided for @deviceJoining.
  ///
  /// In en, this message translates to:
  /// **'Joining'**
  String get deviceJoining;

  /// No description provided for @deviceName.
  ///
  /// In en, this message translates to:
  /// **'Device name'**
  String get deviceName;

  /// No description provided for @deviceReady.
  ///
  /// In en, this message translates to:
  /// **'Waiting for first report'**
  String get deviceReady;

  /// No description provided for @deviceSafeMode.
  ///
  /// In en, this message translates to:
  /// **'Safe mode'**
  String get deviceSafeMode;

  /// No description provided for @deviceUnsupported.
  ///
  /// In en, this message translates to:
  /// **'Unsupported device'**
  String get deviceUnsupported;

  /// No description provided for @diagBootReason.
  ///
  /// In en, this message translates to:
  /// **'Last start'**
  String get diagBootReason;

  /// No description provided for @diagFreeHeap.
  ///
  /// In en, this message translates to:
  /// **'Free memory'**
  String get diagFreeHeap;

  /// No description provided for @diagLastError.
  ///
  /// In en, this message translates to:
  /// **'Last error code'**
  String get diagLastError;

  /// No description provided for @diagRejoins.
  ///
  /// In en, this message translates to:
  /// **'Network rejoins'**
  String get diagRejoins;

  /// No description provided for @diagResets.
  ///
  /// In en, this message translates to:
  /// **'Restarts'**
  String get diagResets;

  /// No description provided for @diagUptime.
  ///
  /// In en, this message translates to:
  /// **'Running for'**
  String get diagUptime;

  /// No description provided for @diagnostics.
  ///
  /// In en, this message translates to:
  /// **'Diagnostics'**
  String get diagnostics;

  /// No description provided for @disableUser.
  ///
  /// In en, this message translates to:
  /// **'Disable'**
  String get disableUser;

  /// No description provided for @enableUser.
  ///
  /// In en, this message translates to:
  /// **'Enable'**
  String get enableUser;

  /// No description provided for @userDisabled.
  ///
  /// In en, this message translates to:
  /// **'disabled'**
  String get userDisabled;

  /// No description provided for @displayName.
  ///
  /// In en, this message translates to:
  /// **'Display name'**
  String get displayName;

  /// No description provided for @done.
  ///
  /// In en, this message translates to:
  /// **'Done'**
  String get done;

  /// No description provided for @editConfig.
  ///
  /// In en, this message translates to:
  /// **'Edit configuration'**
  String get editConfig;

  /// No description provided for @errorAlreadySetUp.
  ///
  /// In en, this message translates to:
  /// **'This gateway is already set up.'**
  String get errorAlreadySetUp;

  /// No description provided for @errorConflict.
  ///
  /// In en, this message translates to:
  /// **'That is not possible right now.'**
  String get errorConflict;

  /// No description provided for @errorDeviceNotReady.
  ///
  /// In en, this message translates to:
  /// **'The device is not ready yet.'**
  String get errorDeviceNotReady;

  /// No description provided for @errorDeviceSafeMode.
  ///
  /// In en, this message translates to:
  /// **'The device is in safe mode and does not water.'**
  String get errorDeviceSafeMode;

  /// No description provided for @errorHubTimeout.
  ///
  /// In en, this message translates to:
  /// **'The gateway did not answer in time. It may still have worked; check again in a moment.'**
  String get errorHubTimeout;

  /// No description provided for @errorHubUnavailable.
  ///
  /// In en, this message translates to:
  /// **'The watering service is not reachable right now.'**
  String get errorHubUnavailable;

  /// No description provided for @errorIncompatibleHub.
  ///
  /// In en, this message translates to:
  /// **'The gateway parts do not fit together. Update the gateway.'**
  String get errorIncompatibleHub;

  /// No description provided for @errorInvalidCredentials.
  ///
  /// In en, this message translates to:
  /// **'Wrong username or password.'**
  String get errorInvalidCredentials;

  /// No description provided for @errorInvalidInvite.
  ///
  /// In en, this message translates to:
  /// **'This invite is not valid (anymore).'**
  String get errorInvalidInvite;

  /// No description provided for @errorInvalidSetupCode.
  ///
  /// In en, this message translates to:
  /// **'The setup code is wrong.'**
  String get errorInvalidSetupCode;

  /// No description provided for @errorNetwork.
  ///
  /// In en, this message translates to:
  /// **'Can\'t reach the gateway.'**
  String get errorNetwork;

  /// No description provided for @errorRateLimited.
  ///
  /// In en, this message translates to:
  /// **'Too many attempts. Wait a moment and try again.'**
  String get errorRateLimited;

  /// No description provided for @errorSlotNotActuator.
  ///
  /// In en, this message translates to:
  /// **'That slot is not a pump.'**
  String get errorSlotNotActuator;

  /// No description provided for @eventsTitle.
  ///
  /// In en, this message translates to:
  /// **'Events'**
  String get eventsTitle;

  /// No description provided for @noEvents.
  ///
  /// In en, this message translates to:
  /// **'No events yet.'**
  String get noEvents;

  /// No description provided for @executionsTitle.
  ///
  /// In en, this message translates to:
  /// **'Recent decisions'**
  String get executionsTitle;

  /// No description provided for @noExecutions.
  ///
  /// In en, this message translates to:
  /// **'The rule has not decided anything yet.'**
  String get noExecutions;

  /// No description provided for @executionWatered.
  ///
  /// In en, this message translates to:
  /// **'Watered'**
  String get executionWatered;

  /// No description provided for @executionSkipped.
  ///
  /// In en, this message translates to:
  /// **'Skipped: {reason}'**
  String executionSkipped(String reason);

  /// No description provided for @skipClock.
  ///
  /// In en, this message translates to:
  /// **'clock not synced'**
  String get skipClock;

  /// No description provided for @skipCooldown.
  ///
  /// In en, this message translates to:
  /// **'too soon after the last watering'**
  String get skipCooldown;

  /// No description provided for @skipDailyLimit.
  ///
  /// In en, this message translates to:
  /// **'daily limit reached'**
  String get skipDailyLimit;

  /// No description provided for @skipNoPump.
  ///
  /// In en, this message translates to:
  /// **'no pump available'**
  String get skipNoPump;

  /// No description provided for @skipPending.
  ///
  /// In en, this message translates to:
  /// **'a watering is already pending'**
  String get skipPending;

  /// No description provided for @skipQuietHours.
  ///
  /// In en, this message translates to:
  /// **'quiet hours'**
  String get skipQuietHours;

  /// No description provided for @skipSensorError.
  ///
  /// In en, this message translates to:
  /// **'sensor problem'**
  String get skipSensorError;

  /// No description provided for @exportTitle.
  ///
  /// In en, this message translates to:
  /// **'Export'**
  String get exportTitle;

  /// No description provided for @exportBody.
  ///
  /// In en, this message translates to:
  /// **'A ZIP file with all plants, devices, readings, commands and users (without passwords). Your password is needed.'**
  String get exportBody;

  /// No description provided for @exportStart.
  ///
  /// In en, this message translates to:
  /// **'Export data'**
  String get exportStart;

  /// No description provided for @exportDone.
  ///
  /// In en, this message translates to:
  /// **'Export downloaded.'**
  String get exportDone;

  /// No description provided for @exportUnsupported.
  ///
  /// In en, this message translates to:
  /// **'Downloading is only supported in the web app for now.'**
  String get exportUnsupported;

  /// No description provided for @fastReportHold.
  ///
  /// In en, this message translates to:
  /// **'Keep fast reports after watering'**
  String get fastReportHold;

  /// No description provided for @fastReportInterval.
  ///
  /// In en, this message translates to:
  /// **'Report interval while watering'**
  String get fastReportInterval;

  /// No description provided for @reportInterval.
  ///
  /// In en, this message translates to:
  /// **'Report interval'**
  String get reportInterval;

  /// No description provided for @reportIntervals.
  ///
  /// In en, this message translates to:
  /// **'Reports'**
  String get reportIntervals;

  /// No description provided for @gatewayApiVersion.
  ///
  /// In en, this message translates to:
  /// **'Web service version'**
  String get gatewayApiVersion;

  /// No description provided for @gatewayCoordinator.
  ///
  /// In en, this message translates to:
  /// **'Zigbee coordinator'**
  String get gatewayCoordinator;

  /// No description provided for @gatewayDatabase.
  ///
  /// In en, this message translates to:
  /// **'Database size'**
  String get gatewayDatabase;

  /// No description provided for @gatewayHub.
  ///
  /// In en, this message translates to:
  /// **'Watering service'**
  String get gatewayHub;

  /// No description provided for @gatewayHubVersion.
  ///
  /// In en, this message translates to:
  /// **'Watering service version'**
  String get gatewayHubVersion;

  /// No description provided for @gatewayServices.
  ///
  /// In en, this message translates to:
  /// **'Services'**
  String get gatewayServices;

  /// No description provided for @gatewayZigbee.
  ///
  /// In en, this message translates to:
  /// **'Zigbee'**
  String get gatewayZigbee;

  /// No description provided for @statusUnknown.
  ///
  /// In en, this message translates to:
  /// **'Unknown'**
  String get statusUnknown;

  /// No description provided for @installCode.
  ///
  /// In en, this message translates to:
  /// **'Install code (optional)'**
  String get installCode;

  /// No description provided for @installCodeHint.
  ///
  /// In en, this message translates to:
  /// **'From the label on the module. Needed for deployed modules.'**
  String get installCodeHint;

  /// No description provided for @installation.
  ///
  /// In en, this message translates to:
  /// **'Installation'**
  String get installation;

  /// No description provided for @installationName.
  ///
  /// In en, this message translates to:
  /// **'Name of this installation'**
  String get installationName;

  /// No description provided for @installationSettings.
  ///
  /// In en, this message translates to:
  /// **'Installation settings'**
  String get installationSettings;

  /// No description provided for @inviteAs.
  ///
  /// In en, this message translates to:
  /// **'Invite as'**
  String get inviteAs;

  /// No description provided for @inviteCreated.
  ///
  /// In en, this message translates to:
  /// **'Invite created'**
  String get inviteCreated;

  /// No description provided for @inviteExpires.
  ///
  /// In en, this message translates to:
  /// **'valid until {time}'**
  String inviteExpires(String time);

  /// No description provided for @inviteShownOnce.
  ///
  /// In en, this message translates to:
  /// **'Send this link to the person. It is shown only once.'**
  String get inviteShownOnce;

  /// No description provided for @invitesTitle.
  ///
  /// In en, this message translates to:
  /// **'Invites'**
  String get invitesTitle;

  /// No description provided for @noInvites.
  ///
  /// In en, this message translates to:
  /// **'No open invites.'**
  String get noInvites;

  /// No description provided for @revokeInvite.
  ///
  /// In en, this message translates to:
  /// **'Revoke invite'**
  String get revokeInvite;

  /// No description provided for @joinAccept.
  ///
  /// In en, this message translates to:
  /// **'Create account'**
  String get joinAccept;

  /// No description provided for @joinClose.
  ///
  /// In en, this message translates to:
  /// **'Close'**
  String get joinClose;

  /// No description provided for @joinConfigure.
  ///
  /// In en, this message translates to:
  /// **'Name and configure'**
  String get joinConfigure;

  /// No description provided for @joinCountdown.
  ///
  /// In en, this message translates to:
  /// **'Open for {time}'**
  String joinCountdown(String time);

  /// No description provided for @joinFailedBody.
  ///
  /// In en, this message translates to:
  /// **'The module could not be set up. Remove it, power-cycle the module and try again.'**
  String get joinFailedBody;

  /// No description provided for @joinIdleTitle.
  ///
  /// In en, this message translates to:
  /// **'Add a device'**
  String get joinIdleTitle;

  /// No description provided for @joinInstallation.
  ///
  /// In en, this message translates to:
  /// **'Join {name}'**
  String joinInstallation(String name);

  /// No description provided for @joinInstructions.
  ///
  /// In en, this message translates to:
  /// **'Open the join window, then power up the module or hold its button for 3 seconds.'**
  String get joinInstructions;

  /// No description provided for @joinOpen.
  ///
  /// In en, this message translates to:
  /// **'Open join window'**
  String get joinOpen;

  /// No description provided for @joinOpenTitle.
  ///
  /// In en, this message translates to:
  /// **'Waiting for the module…'**
  String get joinOpenTitle;

  /// No description provided for @joinRemoveRetry.
  ///
  /// In en, this message translates to:
  /// **'Remove and try again'**
  String get joinRemoveRetry;

  /// No description provided for @joinRole.
  ///
  /// In en, this message translates to:
  /// **'You were invited as {role}.'**
  String joinRole(String role);

  /// No description provided for @joinTitle.
  ///
  /// In en, this message translates to:
  /// **'Join'**
  String get joinTitle;

  /// No description provided for @joinUnsupportedBody.
  ///
  /// In en, this message translates to:
  /// **'This is not a PlantModule ({model}). Remove it.'**
  String joinUnsupportedBody(String model);

  /// No description provided for @stepJoined.
  ///
  /// In en, this message translates to:
  /// **'Joined the network'**
  String get stepJoined;

  /// No description provided for @stepInterviewing.
  ///
  /// In en, this message translates to:
  /// **'Interviewing'**
  String get stepInterviewing;

  /// No description provided for @stepConfiguring.
  ///
  /// In en, this message translates to:
  /// **'Configuring'**
  String get stepConfiguring;

  /// No description provided for @stepReady.
  ///
  /// In en, this message translates to:
  /// **'Ready'**
  String get stepReady;

  /// No description provided for @lastSeenLabel.
  ///
  /// In en, this message translates to:
  /// **'Last seen'**
  String get lastSeenLabel;

  /// No description provided for @lastUsedAgo.
  ///
  /// In en, this message translates to:
  /// **'last used {ago}'**
  String lastUsedAgo(String ago);

  /// No description provided for @neverUsed.
  ///
  /// In en, this message translates to:
  /// **'never used'**
  String get neverUsed;

  /// No description provided for @loginSubtitle.
  ///
  /// In en, this message translates to:
  /// **'Sign in to continue'**
  String get loginSubtitle;

  /// No description provided for @username.
  ///
  /// In en, this message translates to:
  /// **'Username'**
  String get username;

  /// No description provided for @password.
  ///
  /// In en, this message translates to:
  /// **'Password'**
  String get password;

  /// No description provided for @passwordHint.
  ///
  /// In en, this message translates to:
  /// **'At least 8 characters'**
  String get passwordHint;

  /// No description provided for @signIn.
  ///
  /// In en, this message translates to:
  /// **'Sign in'**
  String get signIn;

  /// No description provided for @signOut.
  ///
  /// In en, this message translates to:
  /// **'Sign out'**
  String get signOut;

  /// No description provided for @thisDevice.
  ///
  /// In en, this message translates to:
  /// **'this device'**
  String get thisDevice;

  /// No description provided for @thisDeviceName.
  ///
  /// In en, this message translates to:
  /// **'Name of this device'**
  String get thisDeviceName;

  /// No description provided for @thisDeviceHint.
  ///
  /// In en, this message translates to:
  /// **'Shown in the list of your logins'**
  String get thisDeviceHint;

  /// No description provided for @moduleEmpty.
  ///
  /// In en, this message translates to:
  /// **'Empty'**
  String get moduleEmpty;

  /// No description provided for @moduleMoisture.
  ///
  /// In en, this message translates to:
  /// **'Moisture sensor'**
  String get moduleMoisture;

  /// No description provided for @modulePump.
  ///
  /// In en, this message translates to:
  /// **'Pump'**
  String get modulePump;

  /// No description provided for @slotModule.
  ///
  /// In en, this message translates to:
  /// **'Module'**
  String get slotModule;

  /// No description provided for @slotPort.
  ///
  /// In en, this message translates to:
  /// **'Port'**
  String get slotPort;

  /// No description provided for @portLabel.
  ///
  /// In en, this message translates to:
  /// **'Port {port}'**
  String portLabel(String port);

  /// No description provided for @myDevices.
  ///
  /// In en, this message translates to:
  /// **'My devices'**
  String get myDevices;

  /// No description provided for @revokeToken.
  ///
  /// In en, this message translates to:
  /// **'Sign this device out'**
  String get revokeToken;

  /// No description provided for @noDevicesBody.
  ///
  /// In en, this message translates to:
  /// **'Open the join window and power up a module.'**
  String get noDevicesBody;

  /// No description provided for @noPlantsNoDevices.
  ///
  /// In en, this message translates to:
  /// **'Add a device first, then create your plants.'**
  String get noPlantsNoDevices;

  /// No description provided for @noRulesNoPump.
  ///
  /// In en, this message translates to:
  /// **'This plant has no pump, so it cannot be watered by a rule.'**
  String get noRulesNoPump;

  /// No description provided for @noSlots.
  ///
  /// In en, this message translates to:
  /// **'Nothing is configured yet.'**
  String get noSlots;

  /// No description provided for @notifyFailed.
  ///
  /// In en, this message translates to:
  /// **'When it fails'**
  String get notifyFailed;

  /// No description provided for @notifySkipped.
  ///
  /// In en, this message translates to:
  /// **'When it cannot decide'**
  String get notifySkipped;

  /// No description provided for @notifyWatered.
  ///
  /// In en, this message translates to:
  /// **'When it waters'**
  String get notifyWatered;

  /// No description provided for @ruleNotify.
  ///
  /// In en, this message translates to:
  /// **'Notify'**
  String get ruleNotify;

  /// No description provided for @outOfRange.
  ///
  /// In en, this message translates to:
  /// **'Out of range'**
  String get outOfRange;

  /// No description provided for @pumpActiveHigh.
  ///
  /// In en, this message translates to:
  /// **'Pump switches on with a high signal'**
  String get pumpActiveHigh;

  /// No description provided for @pumpMaxRun.
  ///
  /// In en, this message translates to:
  /// **'Longest run'**
  String get pumpMaxRun;

  /// No description provided for @pumpMinPause.
  ///
  /// In en, this message translates to:
  /// **'Shortest pause between runs'**
  String get pumpMinPause;

  /// No description provided for @quietFrom.
  ///
  /// In en, this message translates to:
  /// **'From {time}'**
  String quietFrom(String time);

  /// No description provided for @quietTo.
  ///
  /// In en, this message translates to:
  /// **'Until {time}'**
  String quietTo(String time);

  /// No description provided for @reauthBody.
  ///
  /// In en, this message translates to:
  /// **'Enter your password to continue.'**
  String get reauthBody;

  /// No description provided for @reauthTitle.
  ///
  /// In en, this message translates to:
  /// **'Confirm with your password'**
  String get reauthTitle;

  /// No description provided for @removeDevice.
  ///
  /// In en, this message translates to:
  /// **'Remove device'**
  String get removeDevice;

  /// No description provided for @removeDeviceBody.
  ///
  /// In en, this message translates to:
  /// **'{name} is removed from the network and its plants lose their sensor and pump. History is kept.'**
  String removeDeviceBody(String name);

  /// No description provided for @removeUser.
  ///
  /// In en, this message translates to:
  /// **'Remove user'**
  String get removeUser;

  /// No description provided for @removeUserBody.
  ///
  /// In en, this message translates to:
  /// **'{name} loses access immediately.'**
  String removeUserBody(String name);

  /// No description provided for @renameDevice.
  ///
  /// In en, this message translates to:
  /// **'Rename'**
  String get renameDevice;

  /// No description provided for @ruleMaxPerDay.
  ///
  /// In en, this message translates to:
  /// **'At most per day'**
  String get ruleMaxPerDay;

  /// No description provided for @ruleMaxPerDayValue.
  ///
  /// In en, this message translates to:
  /// **'at most {count} a day'**
  String ruleMaxPerDayValue(int count);

  /// No description provided for @ruleQuietHours.
  ///
  /// In en, this message translates to:
  /// **'Quiet hours'**
  String get ruleQuietHours;

  /// No description provided for @ruleQuietValue.
  ///
  /// In en, this message translates to:
  /// **'quiet {from} – {to}'**
  String ruleQuietValue(String from, String to);

  /// No description provided for @safeModeBody.
  ///
  /// In en, this message translates to:
  /// **'The module stopped itself ({reason}) and does not water until it is reset.'**
  String safeModeBody(String reason);

  /// No description provided for @safeModeTitle.
  ///
  /// In en, this message translates to:
  /// **'Safe mode'**
  String get safeModeTitle;

  /// No description provided for @saved.
  ///
  /// In en, this message translates to:
  /// **'Saved.'**
  String get saved;

  /// No description provided for @setupCode.
  ///
  /// In en, this message translates to:
  /// **'Setup code'**
  String get setupCode;

  /// No description provided for @setupCodeHint.
  ///
  /// In en, this message translates to:
  /// **'Shown in the log of the web service: docker compose logs api'**
  String get setupCodeHint;

  /// No description provided for @setupCreate.
  ///
  /// In en, this message translates to:
  /// **'Set up this gateway'**
  String get setupCreate;

  /// No description provided for @setupNeedsHub.
  ///
  /// In en, this message translates to:
  /// **'The watering service is not running yet. Setup needs it.'**
  String get setupNeedsHub;

  /// No description provided for @setupSubtitle.
  ///
  /// In en, this message translates to:
  /// **'Create the owner account. This is only needed once.'**
  String get setupSubtitle;

  /// No description provided for @setupTitle.
  ///
  /// In en, this message translates to:
  /// **'Set up this gateway'**
  String get setupTitle;

  /// No description provided for @telegramChat.
  ///
  /// In en, this message translates to:
  /// **'Chat id'**
  String get telegramChat;

  /// No description provided for @telegramConfigured.
  ///
  /// In en, this message translates to:
  /// **'Telegram is set up.'**
  String get telegramConfigured;

  /// No description provided for @telegramNotConfigured.
  ///
  /// In en, this message translates to:
  /// **'Telegram is not set up.'**
  String get telegramNotConfigured;

  /// No description provided for @telegramTitle.
  ///
  /// In en, this message translates to:
  /// **'Telegram'**
  String get telegramTitle;

  /// No description provided for @telegramToken.
  ///
  /// In en, this message translates to:
  /// **'Bot token'**
  String get telegramToken;

  /// No description provided for @telegramTokenHint.
  ///
  /// In en, this message translates to:
  /// **'Leave empty to keep the saved token'**
  String get telegramTokenHint;

  /// No description provided for @timezoneHint.
  ///
  /// In en, this message translates to:
  /// **'For example Europe/Berlin'**
  String get timezoneHint;

  /// No description provided for @transferOwnership.
  ///
  /// In en, this message translates to:
  /// **'Make owner'**
  String get transferOwnership;

  /// No description provided for @transferOwnershipBody.
  ///
  /// In en, this message translates to:
  /// **'{name} becomes the owner. You become an admin.'**
  String transferOwnershipBody(String name);

  /// No description provided for @usersTitle.
  ///
  /// In en, this message translates to:
  /// **'Users'**
  String get usersTitle;

  /// No description provided for @waterQueuedDeviceOffline.
  ///
  /// In en, this message translates to:
  /// **'Watering queued. The device is offline and gets it when it is back.'**
  String get waterQueuedDeviceOffline;

  /// No description provided for @noReadings.
  ///
  /// In en, this message translates to:
  /// **'No readings in this period yet.'**
  String get noReadings;
}

class _AppLocalizationsDelegate
    extends LocalizationsDelegate<AppLocalizations> {
  const _AppLocalizationsDelegate();

  @override
  Future<AppLocalizations> load(Locale locale) {
    return SynchronousFuture<AppLocalizations>(lookupAppLocalizations(locale));
  }

  @override
  bool isSupported(Locale locale) =>
      <String>['de', 'en'].contains(locale.languageCode);

  @override
  bool shouldReload(_AppLocalizationsDelegate old) => false;
}

AppLocalizations lookupAppLocalizations(Locale locale) {
  // Lookup logic when only language code is specified.
  switch (locale.languageCode) {
    case 'de':
      return AppLocalizationsDe();
    case 'en':
      return AppLocalizationsEn();
  }

  throw FlutterError(
    'AppLocalizations.delegate failed to load unsupported locale "$locale". This is likely '
    'an issue with the localizations generation tool. Please file an issue '
    'on GitHub with a reproducible sample app and the gen-l10n configuration '
    'that was used.',
  );
}
