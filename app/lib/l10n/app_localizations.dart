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

  /// No description provided for @switchHousehold.
  ///
  /// In en, this message translates to:
  /// **'Switch household'**
  String get switchHousehold;

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

  /// No description provided for @gatewayOfflineBanner.
  ///
  /// In en, this message translates to:
  /// **'Gateway offline since {time}. Watering is delivered when it\'s back.'**
  String gatewayOfflineBanner(String time);

  /// No description provided for @noPlantsTitle.
  ///
  /// In en, this message translates to:
  /// **'Start with your first plant'**
  String get noPlantsTitle;

  /// No description provided for @noPlantsBody.
  ///
  /// In en, this message translates to:
  /// **'Add a device to start measuring moisture.'**
  String get noPlantsBody;

  /// No description provided for @noHouseholdTitle.
  ///
  /// In en, this message translates to:
  /// **'Create your first household'**
  String get noHouseholdTitle;

  /// No description provided for @noHouseholdBody.
  ///
  /// In en, this message translates to:
  /// **'Or join one with an invite link.'**
  String get noHouseholdBody;

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

  /// No description provided for @errorGatewayOffline.
  ///
  /// In en, this message translates to:
  /// **'The gateway is offline.'**
  String get errorGatewayOffline;

  /// No description provided for @errorTooLate.
  ///
  /// In en, this message translates to:
  /// **'The device already picked this up.'**
  String get errorTooLate;

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

  /// No description provided for @deviceSleeping.
  ///
  /// In en, this message translates to:
  /// **'Sleeping'**
  String get deviceSleeping;

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

  /// No description provided for @batteryValue.
  ///
  /// In en, this message translates to:
  /// **'Battery {percent} %'**
  String batteryValue(int percent);

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
  /// **'Devices sleep between readings. Watering starts on the next wake.'**
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

  /// No description provided for @waterQueuedGatewayOffline.
  ///
  /// In en, this message translates to:
  /// **'Queued. It\'s delivered when the gateway is back online.'**
  String get waterQueuedGatewayOffline;

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

  /// No description provided for @commandQueued.
  ///
  /// In en, this message translates to:
  /// **'Queued · device expected ~{time}'**
  String commandQueued(String time);

  /// No description provided for @commandDelivered.
  ///
  /// In en, this message translates to:
  /// **'Delivered'**
  String get commandDelivered;

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

  /// No description provided for @originLocal.
  ///
  /// In en, this message translates to:
  /// **'On the gateway'**
  String get originLocal;

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

  /// No description provided for @deleteRule.
  ///
  /// In en, this message translates to:
  /// **'Delete rule'**
  String get deleteRule;

  /// No description provided for @ruleSummary.
  ///
  /// In en, this message translates to:
  /// **'Below {percent} % → water {seconds} s, at most every {hours} h'**
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

  /// No description provided for @signalValue.
  ///
  /// In en, this message translates to:
  /// **'Signal {rssi} dBm'**
  String signalValue(int rssi);

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

  /// No description provided for @wakeInterval.
  ///
  /// In en, this message translates to:
  /// **'Wake interval'**
  String get wakeInterval;

  /// No description provided for @everyMinutes.
  ///
  /// In en, this message translates to:
  /// **'every {minutes} min'**
  String everyMinutes(int minutes);

  /// No description provided for @nextExpected.
  ///
  /// In en, this message translates to:
  /// **'Next wake expected'**
  String get nextExpected;

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

  /// No description provided for @pinLabel.
  ///
  /// In en, this message translates to:
  /// **'GPIO {pin}'**
  String pinLabel(int pin);

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

  /// No description provided for @serviceMode.
  ///
  /// In en, this message translates to:
  /// **'Service mode'**
  String get serviceMode;

  /// No description provided for @deviceActionSent.
  ///
  /// In en, this message translates to:
  /// **'Sent. The device acts on its next wake.'**
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

  /// No description provided for @household.
  ///
  /// In en, this message translates to:
  /// **'Household'**
  String get household;

  /// No description provided for @timezone.
  ///
  /// In en, this message translates to:
  /// **'Time zone'**
  String get timezone;

  /// No description provided for @yourRole.
  ///
  /// In en, this message translates to:
  /// **'Your role'**
  String get yourRole;

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

  /// No description provided for @battery.
  ///
  /// In en, this message translates to:
  /// **'Battery'**
  String get battery;

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

  /// No description provided for @gatewayTitle.
  ///
  /// In en, this message translates to:
  /// **'Gateway'**
  String get gatewayTitle;

  /// No description provided for @gatewayNoneTitle.
  ///
  /// In en, this message translates to:
  /// **'Connect your plants'**
  String get gatewayNoneTitle;

  /// No description provided for @gatewayNoneBody.
  ///
  /// In en, this message translates to:
  /// **'Plant devices talk to a gateway: a small computer at home, like a Raspberry Pi, that also runs your watering rules when the internet is down. Start the gateway software, then enter the code it shows.'**
  String get gatewayNoneBody;

  /// No description provided for @gatewayAdd.
  ///
  /// In en, this message translates to:
  /// **'Add gateway'**
  String get gatewayAdd;

  /// No description provided for @gatewayCodeLabel.
  ///
  /// In en, this message translates to:
  /// **'Code shown by the gateway'**
  String get gatewayCodeLabel;

  /// No description provided for @gatewayCodeInvalid.
  ///
  /// In en, this message translates to:
  /// **'Enter the 8-character code, like K7QM-2XPA.'**
  String get gatewayCodeInvalid;

  /// No description provided for @gatewayClaimNote.
  ///
  /// In en, this message translates to:
  /// **'Devices paired before have to be re-paired to the new gateway.'**
  String get gatewayClaimNote;

  /// No description provided for @gatewayAdded.
  ///
  /// In en, this message translates to:
  /// **'Gateway added. Waiting for it to connect.'**
  String get gatewayAdded;

  /// No description provided for @gatewayEnrolling.
  ///
  /// In en, this message translates to:
  /// **'Waiting for the gateway to connect'**
  String get gatewayEnrolling;

  /// No description provided for @gatewayOfflineSince.
  ///
  /// In en, this message translates to:
  /// **'Offline since {time}'**
  String gatewayOfflineSince(String time);

  /// No description provided for @gatewayInSync.
  ///
  /// In en, this message translates to:
  /// **'Settings in sync'**
  String get gatewayInSync;

  /// No description provided for @gatewaySyncing.
  ///
  /// In en, this message translates to:
  /// **'Syncing settings'**
  String get gatewaySyncing;

  /// No description provided for @gatewayVersion.
  ///
  /// In en, this message translates to:
  /// **'Version'**
  String get gatewayVersion;

  /// No description provided for @gatewayAdapters.
  ///
  /// In en, this message translates to:
  /// **'Device types'**
  String get gatewayAdapters;

  /// No description provided for @gatewayUpdateAvailable.
  ///
  /// In en, this message translates to:
  /// **'Update available: {version}'**
  String gatewayUpdateAvailable(String version);

  /// No description provided for @gatewayUpdateHint.
  ///
  /// In en, this message translates to:
  /// **'On the gateway, run: docker compose pull && docker compose up -d'**
  String get gatewayUpdateHint;

  /// No description provided for @gatewayOutbox.
  ///
  /// In en, this message translates to:
  /// **'Messages not uploaded yet'**
  String get gatewayOutbox;

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

  /// No description provided for @gatewayLastReport.
  ///
  /// In en, this message translates to:
  /// **'Last report'**
  String get gatewayLastReport;

  /// No description provided for @gatewayLanAddress.
  ///
  /// In en, this message translates to:
  /// **'LAN address'**
  String get gatewayLanAddress;

  /// No description provided for @gatewayLanHint.
  ///
  /// In en, this message translates to:
  /// **'Devices connect to this address. Override it if the gateway has several network interfaces.'**
  String get gatewayLanHint;

  /// No description provided for @gatewayLanReported.
  ///
  /// In en, this message translates to:
  /// **'Reported by the gateway'**
  String get gatewayLanReported;

  /// No description provided for @gatewayLanOverridden.
  ///
  /// In en, this message translates to:
  /// **'Set manually'**
  String get gatewayLanOverridden;

  /// No description provided for @gatewayLanUnknown.
  ///
  /// In en, this message translates to:
  /// **'Not reported yet'**
  String get gatewayLanUnknown;

  /// No description provided for @gatewayLanReset.
  ///
  /// In en, this message translates to:
  /// **'Use reported address'**
  String get gatewayLanReset;

  /// No description provided for @edit.
  ///
  /// In en, this message translates to:
  /// **'Edit'**
  String get edit;

  /// No description provided for @gatewayRepairTitle.
  ///
  /// In en, this message translates to:
  /// **'Devices to re-pair'**
  String get gatewayRepairTitle;

  /// No description provided for @gatewayRepairBody.
  ///
  /// In en, this message translates to:
  /// **'These devices aren\'t paired to this gateway. Re-pair each one with the phone app, close to the device.'**
  String get gatewayRepairBody;

  /// No description provided for @deviceNeedsRepair.
  ///
  /// In en, this message translates to:
  /// **'Needs re-pairing'**
  String get deviceNeedsRepair;

  /// No description provided for @gatewayRemove.
  ///
  /// In en, this message translates to:
  /// **'Remove gateway'**
  String get gatewayRemove;

  /// No description provided for @gatewayRemoveTitle.
  ///
  /// In en, this message translates to:
  /// **'Remove the gateway?'**
  String get gatewayRemoveTitle;

  /// No description provided for @gatewayRemoveBody.
  ///
  /// In en, this message translates to:
  /// **'Its devices stop reporting until you add a gateway again and re-pair them. Automatic watering stops too. History is kept.'**
  String get gatewayRemoveBody;

  /// No description provided for @gatewayRemoved.
  ///
  /// In en, this message translates to:
  /// **'Gateway removed'**
  String get gatewayRemoved;

  /// No description provided for @gatewayNone.
  ///
  /// In en, this message translates to:
  /// **'No gateway'**
  String get gatewayNone;

  /// No description provided for @errorInvalidCode.
  ///
  /// In en, this message translates to:
  /// **'That code isn\'t valid or has expired. The gateway shows a new one.'**
  String get errorInvalidCode;

  /// No description provided for @errorGatewayExists.
  ///
  /// In en, this message translates to:
  /// **'This household already has a gateway.'**
  String get errorGatewayExists;

  /// No description provided for @errorNoGateway.
  ///
  /// In en, this message translates to:
  /// **'Add a gateway to this household first (Settings → Gateway).'**
  String get errorNoGateway;

  /// No description provided for @errorReauth.
  ///
  /// In en, this message translates to:
  /// **'Sign in again to do this.'**
  String get errorReauth;

  /// No description provided for @pairAddDevice.
  ///
  /// In en, this message translates to:
  /// **'Add device'**
  String get pairAddDevice;

  /// No description provided for @pairWebOnly.
  ///
  /// In en, this message translates to:
  /// **'Adding a device needs Bluetooth. Open the app on your phone.'**
  String get pairWebOnly;

  /// No description provided for @pairLabelTitle.
  ///
  /// In en, this message translates to:
  /// **'Scan the device label'**
  String get pairLabelTitle;

  /// No description provided for @pairLabelBody.
  ///
  /// In en, this message translates to:
  /// **'Hold the camera over the QR code on the label of the plant device.'**
  String get pairLabelBody;

  /// No description provided for @pairManualToggle.
  ///
  /// In en, this message translates to:
  /// **'Enter the code by hand'**
  String get pairManualToggle;

  /// No description provided for @pairManualName.
  ///
  /// In en, this message translates to:
  /// **'Name on the label (MC-XXXX)'**
  String get pairManualName;

  /// No description provided for @pairManualCode.
  ///
  /// In en, this message translates to:
  /// **'Code (26 characters)'**
  String get pairManualCode;

  /// No description provided for @pairLabelInvalid.
  ///
  /// In en, this message translates to:
  /// **'That is not a MoistureController label.'**
  String get pairLabelInvalid;

  /// No description provided for @pairContinue.
  ///
  /// In en, this message translates to:
  /// **'Continue'**
  String get pairContinue;

  /// No description provided for @pairNameTitle.
  ///
  /// In en, this message translates to:
  /// **'Name your device'**
  String get pairNameTitle;

  /// No description provided for @pairNameHint.
  ///
  /// In en, this message translates to:
  /// **'Kitchen window'**
  String get pairNameHint;

  /// No description provided for @pairStart.
  ///
  /// In en, this message translates to:
  /// **'Start pairing'**
  String get pairStart;

  /// No description provided for @pairCreating.
  ///
  /// In en, this message translates to:
  /// **'Adding the device to your household …'**
  String get pairCreating;

  /// No description provided for @pairFinding.
  ///
  /// In en, this message translates to:
  /// **'Looking for {name} …'**
  String pairFinding(String name);

  /// No description provided for @pairHandshake.
  ///
  /// In en, this message translates to:
  /// **'Connecting securely …'**
  String get pairHandshake;

  /// No description provided for @pairScanning.
  ///
  /// In en, this message translates to:
  /// **'Looking for WiFi networks …'**
  String get pairScanning;

  /// No description provided for @pairWifiTitle.
  ///
  /// In en, this message translates to:
  /// **'Choose the WiFi for the device'**
  String get pairWifiTitle;

  /// No description provided for @pairWifiBody.
  ///
  /// In en, this message translates to:
  /// **'It must be the network your gateway is on.'**
  String get pairWifiBody;

  /// No description provided for @pairSsidLabel.
  ///
  /// In en, this message translates to:
  /// **'Network name'**
  String get pairSsidLabel;

  /// No description provided for @pairPasswordLabel.
  ///
  /// In en, this message translates to:
  /// **'WiFi password'**
  String get pairPasswordLabel;

  /// No description provided for @pairConnect.
  ///
  /// In en, this message translates to:
  /// **'Connect and test'**
  String get pairConnect;

  /// No description provided for @pairTestingTitle.
  ///
  /// In en, this message translates to:
  /// **'Testing the connection …'**
  String get pairTestingTitle;

  /// No description provided for @pairTestingBody.
  ///
  /// In en, this message translates to:
  /// **'The device joins the WiFi and contacts your gateway. This takes up to 40 seconds.'**
  String get pairTestingBody;

  /// No description provided for @pairTestWifiFailed.
  ///
  /// In en, this message translates to:
  /// **'The device could not join the WiFi. Check the name and the password.'**
  String get pairTestWifiFailed;

  /// No description provided for @pairTestMqttFailed.
  ///
  /// In en, this message translates to:
  /// **'The device joined the WiFi but could not reach the gateway ({detail}).'**
  String pairTestMqttFailed(String detail);

  /// No description provided for @pairFinishing.
  ///
  /// In en, this message translates to:
  /// **'Finishing up …'**
  String get pairFinishing;

  /// No description provided for @pairWaitingOnline.
  ///
  /// In en, this message translates to:
  /// **'Waiting for the device to report in …'**
  String get pairWaitingOnline;

  /// No description provided for @pairDoneTitle.
  ///
  /// In en, this message translates to:
  /// **'Device added'**
  String get pairDoneTitle;

  /// No description provided for @pairDoneBody.
  ///
  /// In en, this message translates to:
  /// **'{name} is connected.'**
  String pairDoneBody(String name);

  /// No description provided for @pairDoneSlow.
  ///
  /// In en, this message translates to:
  /// **'The device was added but has not reported in yet. It should show up online within a few minutes.'**
  String get pairDoneSlow;

  /// No description provided for @pairOpenDevice.
  ///
  /// In en, this message translates to:
  /// **'Open device'**
  String get pairOpenDevice;

  /// No description provided for @pairFailNoGateway.
  ///
  /// In en, this message translates to:
  /// **'Add a gateway to this household first (Settings → Gateway).'**
  String get pairFailNoGateway;

  /// No description provided for @pairFailGatewayOffline.
  ///
  /// In en, this message translates to:
  /// **'The gateway is offline. Bring it online first.'**
  String get pairFailGatewayOffline;

  /// No description provided for @pairFailNotFound.
  ///
  /// In en, this message translates to:
  /// **'No device found. A new device advertises by itself; a paired one needs the BOOT button held for 3 seconds.'**
  String get pairFailNotFound;

  /// No description provided for @pairFailWrongCode.
  ///
  /// In en, this message translates to:
  /// **'Wrong device or wrong code. The device was removed again.'**
  String get pairFailWrongCode;

  /// No description provided for @pairFailConnection.
  ///
  /// In en, this message translates to:
  /// **'The connection to the device was lost.'**
  String get pairFailConnection;

  /// No description provided for @pairFailBluetoothOff.
  ///
  /// In en, this message translates to:
  /// **'Bluetooth is off. Turn it on and try again.'**
  String get pairFailBluetoothOff;

  /// No description provided for @pairFailBluetoothDenied.
  ///
  /// In en, this message translates to:
  /// **'The app needs permission to use Bluetooth. Allow it in the system settings.'**
  String get pairFailBluetoothDenied;

  /// No description provided for @pairFailUnsupported.
  ///
  /// In en, this message translates to:
  /// **'This device cannot pair over Bluetooth. Use the mobile app.'**
  String get pairFailUnsupported;

  /// No description provided for @pairFailOther.
  ///
  /// In en, this message translates to:
  /// **'Something went wrong.'**
  String get pairFailOther;

  /// No description provided for @pairTryAgain.
  ///
  /// In en, this message translates to:
  /// **'Try again'**
  String get pairTryAgain;

  /// No description provided for @pairClose.
  ///
  /// In en, this message translates to:
  /// **'Close'**
  String get pairClose;

  /// No description provided for @pairCancelTitle.
  ///
  /// In en, this message translates to:
  /// **'Cancel pairing?'**
  String get pairCancelTitle;

  /// No description provided for @pairCancelBody.
  ///
  /// In en, this message translates to:
  /// **'The device is removed from your household again.'**
  String get pairCancelBody;

  /// No description provided for @pairKeepGoing.
  ///
  /// In en, this message translates to:
  /// **'Keep going'**
  String get pairKeepGoing;
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
