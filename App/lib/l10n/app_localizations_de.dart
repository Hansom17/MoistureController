// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for German (`de`).
class AppLocalizationsDe extends AppLocalizations {
  AppLocalizationsDe([String locale = 'de']) : super(locale);

  @override
  String get appTitle => 'Moisture';

  @override
  String get navPlants => 'Pflanzen';

  @override
  String get navDevices => 'Geräte';

  @override
  String get navAlerts => 'Hinweise';

  @override
  String get navSettings => 'Einstellungen';

  @override
  String get roleViewer => 'Betrachter';

  @override
  String get roleMember => 'Mitglied';

  @override
  String get roleAdmin => 'Admin';

  @override
  String get roleOwner => 'Eigentümer';

  @override
  String get noPlantsTitle => 'Starte mit deiner ersten Pflanze';

  @override
  String get retry => 'Erneut versuchen';

  @override
  String get errorGeneric => 'Etwas ist schiefgelaufen.';

  @override
  String get errorForbidden => 'Deine Rolle erlaubt das nicht mehr.';

  @override
  String get errorSafetyLimit => 'Das ist länger als das Limit dieser Pumpe.';

  @override
  String get errorBusy =>
      'Das Gerät ist beschäftigt. Versuch es gleich noch einmal.';

  @override
  String moistureSemantics(int percent) {
    return 'Feuchtigkeit $percent Prozent';
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
  String get justNow => 'gerade eben';

  @override
  String minutesAgo(int n) {
    return 'vor $n Min.';
  }

  @override
  String hoursAgo(int n) {
    return 'vor $n Std.';
  }

  @override
  String daysAgo(int n) {
    return 'vor $n T.';
  }

  @override
  String get deviceOnline => 'Online';

  @override
  String get deviceLate => 'Verspätet';

  @override
  String get deviceOffline => 'Offline';

  @override
  String lastSeen(String ago) {
    return 'zuletzt $ago';
  }

  @override
  String lastReading(String ago) {
    return 'Letzte Messung $ago';
  }

  @override
  String get trendFalling => 'Trocknet';

  @override
  String get trendSteady => 'Stabil';

  @override
  String get trendRising => 'Steigt';

  @override
  String get pendingCommand => 'Gießen ausstehend';

  @override
  String get waterNow => 'Jetzt gießen';

  @override
  String waterFor(int seconds) {
    return '$seconds s gießen';
  }

  @override
  String waterSheetTitle(String plant) {
    return '$plant gießen';
  }

  @override
  String get waterSheetHint =>
      'Das Gießen startet, sobald das Modul bestätigt. Ist es offline, wird es gesendet, sobald es zurück ist.';

  @override
  String pumpLimit(int seconds) {
    return 'Pumpenlimit: $seconds s';
  }

  @override
  String get waterQueued => 'Gießen eingeplant';

  @override
  String get cancel => 'Abbrechen';

  @override
  String get cancelCommand => 'Gießen abbrechen';

  @override
  String get cancelCommandHint =>
      'Ohne Gewähr — es kann bereits gelaufen sein.';

  @override
  String commandTitle(int seconds) {
    return '$seconds s gießen';
  }

  @override
  String commandRunning(String time) {
    return 'Läuft bis $time';
  }

  @override
  String get commandDone => 'Fertig';

  @override
  String get commandFailed => 'Fehlgeschlagen';

  @override
  String get commandExpired => 'Abgelaufen';

  @override
  String get commandCancelled => 'Abgebrochen';

  @override
  String get originUser => 'Manuell';

  @override
  String get originRule => 'Regel';

  @override
  String get historyTitle => 'Feuchtigkeitsverlauf';

  @override
  String get range24h => '24 h';

  @override
  String get range7d => '7 T';

  @override
  String get range30d => '30 T';

  @override
  String get range1y => '1 J';

  @override
  String chartSummary(int min, int max) {
    return 'Feuchtigkeit zwischen $min und $max % in diesem Zeitraum';
  }

  @override
  String get commandsTitle => 'Gießen';

  @override
  String get noCommands => 'Noch nicht gegossen.';

  @override
  String get rulesTitle => 'Regeln';

  @override
  String get noRules => 'Füge eine Regel hinzu, um automatisch zu gießen.';

  @override
  String get addRule => 'Regel hinzufügen';

  @override
  String get editRule => 'Regel bearbeiten';

  @override
  String ruleSummary(int percent, int seconds, int hours) {
    return 'Unter $percent %: $seconds s gießen, höchstens alle $hours h';
  }

  @override
  String get ruleBelow => 'Gießen, wenn Feuchtigkeit unter';

  @override
  String get ruleDuration => 'Gießdauer';

  @override
  String get ruleInterval => 'Höchstens alle';

  @override
  String get ruleEnabled => 'Regel aktiv';

  @override
  String get save => 'Speichern';

  @override
  String get delete => 'Löschen';

  @override
  String get noDevices => 'Füge dein erstes Gerät hinzu';

  @override
  String firmwareValue(String version) {
    return 'Firmware $version';
  }

  @override
  String get configInSync => 'Konfiguration aktuell';

  @override
  String configPending(int rev) {
    return 'Konfiguration ausstehend (Rev. $rev)';
  }

  @override
  String get configRejected => 'Konfiguration abgelehnt';

  @override
  String get deviceDetails => 'Details';

  @override
  String get board => 'Board';

  @override
  String get slots => 'Steckplätze';

  @override
  String slotLabel(int index) {
    return 'Steckplatz $index';
  }

  @override
  String get identify => 'Identifizieren';

  @override
  String get reboot => 'Neustart';

  @override
  String get deviceActionSent => 'An das Gerät gesendet.';

  @override
  String get openAlerts => 'Offen';

  @override
  String get closedAlerts => 'Erledigt';

  @override
  String get noAlerts => 'Allen Pflanzen geht es gut';

  @override
  String alertDeviceOffline(String subject) {
    return '$subject ist offline';
  }

  @override
  String alertBatteryLow(String subject) {
    return '$subject: Akku schwach';
  }

  @override
  String alertSensorSuspect(String subject) {
    return '$subject: Sensorwerte sehen falsch aus';
  }

  @override
  String alertCommandFailed(String subject) {
    return '$subject: Gießen fehlgeschlagen';
  }

  @override
  String get acknowledge => 'Bestätigen';

  @override
  String acknowledgedAgo(String ago) {
    return 'Bestätigt $ago';
  }

  @override
  String get appearance => 'Darstellung';

  @override
  String get themeSystem => 'System';

  @override
  String get themeLight => 'Hell';

  @override
  String get themeDark => 'Dunkel';

  @override
  String get language => 'Sprache';

  @override
  String get timezone => 'Zeitzone';

  @override
  String get demoSection => 'Demo';

  @override
  String get demoRole => 'Demo-Rolle in diesem Haushalt';

  @override
  String get demoRoleHint => 'Nur im Dev-Build ohne Backend.';

  @override
  String get notAllowed => 'Deine Rolle erlaubt das nicht.';

  @override
  String get signal => 'Signal';

  @override
  String get firmware => 'Firmware';

  @override
  String get noReading => 'Noch keine Messung';

  @override
  String alertOther(String subject, String kind) {
    return '$subject: $kind';
  }

  @override
  String get gatewayClock => 'Uhrzeit';

  @override
  String get gatewayClockOk => 'Synchron';

  @override
  String get gatewayClockBad => 'Nicht synchron: kein automatisches Gießen';

  @override
  String get errorReauth => 'Melde dich erneut an, um das zu tun.';

  @override
  String get serverTitle => 'Server';

  @override
  String get connSearching => 'Suche den Server in deinem Netzwerk …';

  @override
  String get connUnreachable => 'Der Server ist nicht erreichbar.';

  @override
  String get connChoose => 'Mehrere Server gefunden. Wähle einen aus.';

  @override
  String get connEnterAddress => 'Adresse eingeben';

  @override
  String get serverCurrent => 'Verbunden mit';

  @override
  String get serverFound => 'Server in deinem Netzwerk';

  @override
  String get serverSearchAgain => 'Erneut suchen';

  @override
  String get serverAddress => 'Serveradresse';

  @override
  String get serverAddressHint => '192.168.1.10:8000';

  @override
  String get serverAddressInvalid => 'Das ist keine gültige Adresse.';

  @override
  String get serverAddressNotLocal =>
      'Nur Adressen in deinem Heimnetz sind erlaubt.';

  @override
  String get serverAddressNoAnswer => 'Dort antwortet kein Moisture-Server.';

  @override
  String get serverAuthDev => 'Dev-Login (ohne Passwort)';

  @override
  String get serverAuthFirebase => 'Firebase-Login';

  @override
  String get serverDevWarningTitle => 'Ungesicherter Dev-Login';

  @override
  String get serverDevWarningBody =>
      'Dieser Server akzeptiert Logins ohne Passwort. Verbinde dich nur, wenn es dein eigener Entwicklungsserver ist.';

  @override
  String get serverContinue => 'Verbinden';

  @override
  String get serverUseThis => 'Diesen Server verwenden';

  @override
  String get commandQueued => 'Eingeplant';

  @override
  String signalValue(int quality) {
    return 'Verbindungsqualität $quality';
  }

  @override
  String get noPlantsBody =>
      'Lege eine Pflanze für einen Sensor eines deiner Geräte an.';

  @override
  String get serverSubtitle => 'Das Gateway, mit dem die App spricht';

  @override
  String get gatewayTitle => 'Gateway';

  @override
  String get commandDelivered => 'Läuft';

  @override
  String get account => 'Konto';

  @override
  String get addDevice => 'Gerät hinzufügen';

  @override
  String get addPlant => 'Pflanze hinzufügen';

  @override
  String get editPlant => 'Pflanze bearbeiten';

  @override
  String get plantName => 'Name';

  @override
  String get plantSensor => 'Feuchtesensor';

  @override
  String get plantPump => 'Pumpe';

  @override
  String get plantNoSlots =>
      'Noch kein Gerät hat einen Sensor oder eine Pumpe eingerichtet. Richte zuerst ein Gerät ein.';

  @override
  String alertSafeMode(String subject) {
    return '$subject ist im abgesicherten Modus';
  }

  @override
  String get alertZigbeeOffline => 'Zigbee läuft nicht';

  @override
  String get auditTitle => 'Aktivität';

  @override
  String get noAudit => 'Noch nichts.';

  @override
  String get backupTitle => 'Sicherung';

  @override
  String get backupBody =>
      'Legt eine konsistente Kopie der Datenbanken auf dem Gateway an. Die Zigbee-Netzwerkdaten müssen separat gesichert werden (scripts/backup.sh).';

  @override
  String get backupNow => 'Jetzt sichern';

  @override
  String get backupDone => 'Sicherung auf dem Gateway angelegt.';

  @override
  String get bannerHubDown =>
      'Der Gießdienst ist nicht erreichbar. Du siehst die letzten bekannten Daten; Änderungen sind nicht möglich.';

  @override
  String get bannerZigbeeDown =>
      'Zigbee läuft nicht. Daten und Befehle sind pausiert.';

  @override
  String get batteryThreshold => 'Akku schwach (mV)';

  @override
  String get calDry => 'Trockenwert (roh)';

  @override
  String get calWet => 'Nasswert (roh)';

  @override
  String get changePassword => 'Passwort ändern';

  @override
  String get currentPassword => 'Aktuelles Passwort';

  @override
  String get newPassword => 'Neues Passwort';

  @override
  String get passwordChangeHint =>
      'Beim Ändern werden deine anderen Geräte abgemeldet.';

  @override
  String get passwordChanged => 'Passwort geändert.';

  @override
  String get changeRole => 'Rolle ändern';

  @override
  String get channelApp => 'In der App';

  @override
  String get channelTelegram => 'Telegram';

  @override
  String get clearSafeMode => 'Abgesicherten Modus beenden';

  @override
  String get commandQueuedOffline => 'Eingeplant · Gerät offline';

  @override
  String get configApplyNote =>
      'Die Änderung wird übernommen, sobald das Gerät sie bestätigt.';

  @override
  String get configConflict =>
      'Jemand hat dieses Gerät inzwischen geändert. Die aktuelle Konfiguration wurde geladen; bitte prüfen und erneut speichern.';

  @override
  String get configNoBoard =>
      'Dieses Gerät hat seine Platine noch nicht gemeldet.';

  @override
  String configPendingBody(int rev) {
    return 'Revision $rev wartet auf die Bestätigung des Geräts.';
  }

  @override
  String configRejectedBody(String error) {
    return 'Das Gerät hat die Konfiguration abgelehnt: $error';
  }

  @override
  String get configRevert => 'Laufende Konfiguration übernehmen';

  @override
  String get configRevision => 'Konfiguration (läuft / gesendet)';

  @override
  String get configSaved => 'Konfiguration an das Gerät gesendet.';

  @override
  String get confirm => 'Bestätigen';

  @override
  String get copied => 'Kopiert.';

  @override
  String get copyLink => 'Link kopieren';

  @override
  String get createInvite => 'Einladung erstellen';

  @override
  String get dataTitle => 'Sicherung und Export';

  @override
  String get deviceJoinFailed => 'Beitritt fehlgeschlagen';

  @override
  String get deviceJoining => 'Tritt bei';

  @override
  String get deviceName => 'Gerätename';

  @override
  String get deviceReady => 'Wartet auf ersten Bericht';

  @override
  String get deviceSafeMode => 'Abgesicherter Modus';

  @override
  String get deviceUnsupported => 'Nicht unterstütztes Gerät';

  @override
  String get diagBootReason => 'Letzter Start';

  @override
  String get diagFreeHeap => 'Freier Speicher';

  @override
  String get diagLastError => 'Letzter Fehlercode';

  @override
  String get diagRejoins => 'Netzwerk-Wiederbeitritte';

  @override
  String get diagResets => 'Neustarts';

  @override
  String get diagUptime => 'Läuft seit';

  @override
  String get diagnostics => 'Diagnose';

  @override
  String get disableUser => 'Sperren';

  @override
  String get enableUser => 'Entsperren';

  @override
  String get userDisabled => 'gesperrt';

  @override
  String get displayName => 'Anzeigename';

  @override
  String get done => 'Fertig';

  @override
  String get editConfig => 'Konfiguration bearbeiten';

  @override
  String get errorAlreadySetUp => 'Dieses Gateway ist schon eingerichtet.';

  @override
  String get errorConflict => 'Das ist gerade nicht möglich.';

  @override
  String get errorDeviceNotReady => 'Das Gerät ist noch nicht bereit.';

  @override
  String get errorDeviceSafeMode =>
      'Das Gerät ist im abgesicherten Modus und gießt nicht.';

  @override
  String get errorHubTimeout =>
      'Das Gateway hat nicht rechtzeitig geantwortet. Es kann trotzdem geklappt haben; prüfe es gleich noch einmal.';

  @override
  String get errorHubUnavailable =>
      'Der Gießdienst ist gerade nicht erreichbar.';

  @override
  String get errorIncompatibleHub =>
      'Die Teile des Gateways passen nicht zusammen. Aktualisiere das Gateway.';

  @override
  String get errorInvalidCredentials => 'Benutzername oder Passwort falsch.';

  @override
  String get errorInvalidInvite => 'Diese Einladung ist nicht (mehr) gültig.';

  @override
  String get errorInvalidSetupCode => 'Der Einrichtungscode ist falsch.';

  @override
  String get errorNetwork => 'Das Gateway ist nicht erreichbar.';

  @override
  String get errorRateLimited =>
      'Zu viele Versuche. Warte einen Moment und versuche es erneut.';

  @override
  String get errorSlotNotActuator => 'Dieser Steckplatz ist keine Pumpe.';

  @override
  String get eventsTitle => 'Ereignisse';

  @override
  String get noEvents => 'Noch keine Ereignisse.';

  @override
  String get executionsTitle => 'Letzte Entscheidungen';

  @override
  String get noExecutions => 'Die Regel hat noch nichts entschieden.';

  @override
  String get executionWatered => 'Gegossen';

  @override
  String executionSkipped(String reason) {
    return 'Übersprungen: $reason';
  }

  @override
  String get skipClock => 'Uhr nicht synchron';

  @override
  String get skipCooldown => 'zu kurz nach dem letzten Gießen';

  @override
  String get skipDailyLimit => 'Tageslimit erreicht';

  @override
  String get skipNoPump => 'keine Pumpe verfügbar';

  @override
  String get skipPending => 'ein Gießen ist schon offen';

  @override
  String get skipQuietHours => 'Ruhezeit';

  @override
  String get skipSensorError => 'Sensorproblem';

  @override
  String get exportTitle => 'Export';

  @override
  String get exportBody =>
      'Eine ZIP-Datei mit allen Pflanzen, Geräten, Messwerten, Befehlen und Benutzern (ohne Passwörter). Dein Passwort wird benötigt.';

  @override
  String get exportStart => 'Daten exportieren';

  @override
  String get exportDone => 'Export heruntergeladen.';

  @override
  String get exportUnsupported =>
      'Der Download wird vorerst nur in der Web-App unterstützt.';

  @override
  String get fastReportHold => 'Schnelle Berichte nach dem Gießen';

  @override
  String get fastReportInterval => 'Berichtsintervall beim Gießen';

  @override
  String get reportInterval => 'Berichtsintervall';

  @override
  String get reportIntervals => 'Berichte';

  @override
  String get gatewayApiVersion => 'Version Webdienst';

  @override
  String get gatewayCoordinator => 'Zigbee-Koordinator';

  @override
  String get gatewayDatabase => 'Größe der Datenbank';

  @override
  String get gatewayHub => 'Gießdienst';

  @override
  String get gatewayHubVersion => 'Version Gießdienst';

  @override
  String get gatewayServices => 'Dienste';

  @override
  String get gatewayZigbee => 'Zigbee';

  @override
  String get statusUnknown => 'Unbekannt';

  @override
  String get installCode => 'Installationscode (optional)';

  @override
  String get installCodeHint =>
      'Vom Aufkleber auf dem Modul. Bei fertigen Modulen erforderlich.';

  @override
  String get installation => 'Installation';

  @override
  String get installationName => 'Name dieser Installation';

  @override
  String get installationSettings => 'Einstellungen der Installation';

  @override
  String get inviteAs => 'Einladen als';

  @override
  String get inviteCreated => 'Einladung erstellt';

  @override
  String inviteExpires(String time) {
    return 'gültig bis $time';
  }

  @override
  String get inviteShownOnce =>
      'Schicke diesen Link an die Person. Er wird nur einmal angezeigt.';

  @override
  String get invitesTitle => 'Einladungen';

  @override
  String get noInvites => 'Keine offenen Einladungen.';

  @override
  String get revokeInvite => 'Einladung zurückziehen';

  @override
  String get joinAccept => 'Konto erstellen';

  @override
  String get joinClose => 'Schließen';

  @override
  String get joinConfigure => 'Benennen und konfigurieren';

  @override
  String joinCountdown(String time) {
    return 'Noch offen: $time';
  }

  @override
  String get joinFailedBody =>
      'Das Modul konnte nicht eingerichtet werden. Entferne es, schalte das Modul aus und wieder ein und versuche es erneut.';

  @override
  String get joinIdleTitle => 'Ein Gerät hinzufügen';

  @override
  String joinInstallation(String name) {
    return '$name beitreten';
  }

  @override
  String get joinInstructions =>
      'Öffne das Beitrittsfenster und schalte dann das Modul ein oder halte seinen Knopf 3 Sekunden gedrückt.';

  @override
  String get joinOpen => 'Beitrittsfenster öffnen';

  @override
  String get joinOpenTitle => 'Warte auf das Modul…';

  @override
  String get joinRemoveRetry => 'Entfernen und erneut versuchen';

  @override
  String joinRole(String role) {
    return 'Du wurdest als $role eingeladen.';
  }

  @override
  String get joinTitle => 'Beitreten';

  @override
  String joinUnsupportedBody(String model) {
    return 'Das ist kein PlantModule ($model). Entferne es.';
  }

  @override
  String get stepJoined => 'Im Netzwerk';

  @override
  String get stepInterviewing => 'Wird abgefragt';

  @override
  String get stepConfiguring => 'Wird eingerichtet';

  @override
  String get stepReady => 'Bereit';

  @override
  String get lastSeenLabel => 'Zuletzt gesehen';

  @override
  String lastUsedAgo(String ago) {
    return 'zuletzt benutzt $ago';
  }

  @override
  String get neverUsed => 'nie benutzt';

  @override
  String get loginSubtitle => 'Melde dich an, um fortzufahren';

  @override
  String get username => 'Benutzername';

  @override
  String get password => 'Passwort';

  @override
  String get passwordHint => 'Mindestens 8 Zeichen';

  @override
  String get signIn => 'Anmelden';

  @override
  String get signOut => 'Abmelden';

  @override
  String get thisDevice => 'dieses Gerät';

  @override
  String get thisDeviceName => 'Name dieses Geräts';

  @override
  String get thisDeviceHint => 'Wird in der Liste deiner Anmeldungen angezeigt';

  @override
  String get moduleEmpty => 'Leer';

  @override
  String get moduleMoisture => 'Feuchtesensor';

  @override
  String get modulePump => 'Pumpe';

  @override
  String get slotModule => 'Modul';

  @override
  String get slotPort => 'Anschluss';

  @override
  String portLabel(String port) {
    return 'Anschluss $port';
  }

  @override
  String get myDevices => 'Meine Geräte';

  @override
  String get revokeToken => 'Dieses Gerät abmelden';

  @override
  String get noDevicesBody =>
      'Öffne das Beitrittsfenster und schalte ein Modul ein.';

  @override
  String get noPlantsNoDevices =>
      'Füge zuerst ein Gerät hinzu und lege dann deine Pflanzen an.';

  @override
  String get noRulesNoPump =>
      'Diese Pflanze hat keine Pumpe und kann daher nicht per Regel gegossen werden.';

  @override
  String get noSlots => 'Noch nichts eingerichtet.';

  @override
  String get notifyFailed => 'Bei Fehlern';

  @override
  String get notifySkipped => 'Wenn sie nicht entscheiden kann';

  @override
  String get notifyWatered => 'Wenn sie gießt';

  @override
  String get ruleNotify => 'Benachrichtigen';

  @override
  String get outOfRange => 'Außerhalb des Bereichs';

  @override
  String get pumpActiveHigh => 'Pumpe schaltet bei hohem Signal ein';

  @override
  String get pumpMaxRun => 'Längste Laufzeit';

  @override
  String get pumpMinPause => 'Kürzeste Pause zwischen Läufen';

  @override
  String quietFrom(String time) {
    return 'Ab $time';
  }

  @override
  String quietTo(String time) {
    return 'Bis $time';
  }

  @override
  String get reauthBody => 'Gib dein Passwort ein, um fortzufahren.';

  @override
  String get reauthTitle => 'Mit Passwort bestätigen';

  @override
  String get removeDevice => 'Gerät entfernen';

  @override
  String removeDeviceBody(String name) {
    return '$name wird aus dem Netzwerk entfernt und seine Pflanzen verlieren Sensor und Pumpe. Der Verlauf bleibt erhalten.';
  }

  @override
  String get removeUser => 'Benutzer entfernen';

  @override
  String removeUserBody(String name) {
    return '$name verliert sofort den Zugang.';
  }

  @override
  String get renameDevice => 'Umbenennen';

  @override
  String get ruleMaxPerDay => 'Höchstens pro Tag';

  @override
  String ruleMaxPerDayValue(int count) {
    return 'höchstens $count pro Tag';
  }

  @override
  String get ruleQuietHours => 'Ruhezeit';

  @override
  String ruleQuietValue(String from, String to) {
    return 'Ruhe $from – $to';
  }

  @override
  String safeModeBody(String reason) {
    return 'Das Modul hat sich selbst gestoppt ($reason) und gießt nicht, bis es zurückgesetzt wird.';
  }

  @override
  String get safeModeTitle => 'Abgesicherter Modus';

  @override
  String get saved => 'Gespeichert.';

  @override
  String get setupCode => 'Einrichtungscode';

  @override
  String get setupCodeHint =>
      'Steht im Log des Webdienstes: docker compose logs api';

  @override
  String get setupCreate => 'Dieses Gateway einrichten';

  @override
  String get setupNeedsHub =>
      'Der Gießdienst läuft noch nicht. Die Einrichtung braucht ihn.';

  @override
  String get setupSubtitle =>
      'Lege das Besitzerkonto an. Das ist nur einmal nötig.';

  @override
  String get setupTitle => 'Dieses Gateway einrichten';

  @override
  String get telegramChat => 'Chat-ID';

  @override
  String get telegramConfigured => 'Telegram ist eingerichtet.';

  @override
  String get telegramNotConfigured => 'Telegram ist nicht eingerichtet.';

  @override
  String get telegramTitle => 'Telegram';

  @override
  String get telegramToken => 'Bot-Token';

  @override
  String get telegramTokenHint =>
      'Leer lassen, um den gespeicherten Token zu behalten';

  @override
  String get timezoneHint => 'Zum Beispiel Europe/Berlin';

  @override
  String get transferOwnership => 'Zum Besitzer machen';

  @override
  String transferOwnershipBody(String name) {
    return '$name wird Besitzer. Du wirst Admin.';
  }

  @override
  String get usersTitle => 'Benutzer';

  @override
  String get waterQueuedDeviceOffline =>
      'Gießen eingeplant. Das Gerät ist offline und bekommt es, sobald es zurück ist.';

  @override
  String get noReadings => 'In diesem Zeitraum gibt es noch keine Messwerte.';

  @override
  String get batteryTitle => 'Akku';

  @override
  String get batteryStateOk => 'OK';

  @override
  String get batteryStateLow => 'Schwach';

  @override
  String get batteryStateCritical => 'Kritisch';

  @override
  String get batteryStateAbsent => 'Kein Akku';

  @override
  String batteryPercent(int percent) {
    return 'ca. $percent %';
  }

  @override
  String batteryVolts(String volts) {
    return '$volts V';
  }

  @override
  String get batteryChargingHint => 'Laden kann nicht erkannt werden.';

  @override
  String batteryCalibrated(String delta) {
    return 'Kalibriert ($delta)';
  }

  @override
  String get calibrateBattery => 'Akku kalibrieren';

  @override
  String calibrateBatteryBody(String volts) {
    return 'Miss die Zelle mit einem Multimeter und gib den Wert ein. Das Modul meldet jetzt $volts V. Werte mit mehr als 10 % Abweichung werden abgelehnt.';
  }

  @override
  String get measuredVolts => 'Gemessene Spannung';

  @override
  String get calibrate => 'Kalibrieren';

  @override
  String get batteryCalibrationSent => 'Kalibrierung an das Gerät gesendet.';

  @override
  String get batteryNoData => 'Noch keine Akkuwerte.';

  @override
  String get batteryCriticalThreshold => 'Akku kritisch (mV)';

  @override
  String get batteryThresholdsHint =>
      'Gilt für alle Geräte, sobald sie es bestätigen.';

  @override
  String get batteryThresholdsInvalid =>
      'Kritisch muss unter schwach liegen, beide zwischen 3000 und 4000 mV.';

  @override
  String get batteryCell => 'Li-Ion / LiPo, eine Zelle';

  @override
  String alertBatteryCritical(String subject) {
    return '$subject: Akku kritisch';
  }

  @override
  String get commandFailedBattery => 'Akku zu schwach zum Gießen';

  @override
  String get waterBatteryHint =>
      'Der Akku dieses Moduls ist kritisch: Es verweigert das Gießen.';

  @override
  String get batteryVoltage => 'Spannung';

  @override
  String get batteryLevel => 'Stand (geschätzt)';

  @override
  String get plantMenu => 'Pflanzenmenü';

  @override
  String get readNow => 'Jetzt messen';

  @override
  String get readingRequested =>
      'Messung angefordert. Der Wert kommt in wenigen Sekunden.';
}
