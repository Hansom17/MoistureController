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
  String get switchHousehold => 'Haushalt wechseln';

  @override
  String get roleViewer => 'Betrachter';

  @override
  String get roleMember => 'Mitglied';

  @override
  String get roleAdmin => 'Admin';

  @override
  String get roleOwner => 'Eigentümer';

  @override
  String hubOfflineBanner(String time) {
    return 'Hub offline seit $time. Gießen wird ausgeführt, sobald er wieder da ist.';
  }

  @override
  String get noPlantsTitle => 'Starte mit deiner ersten Pflanze';

  @override
  String get noPlantsBody => 'Füge ein Gerät hinzu, um Feuchtigkeit zu messen.';

  @override
  String get noHouseholdTitle => 'Lege deinen ersten Haushalt an';

  @override
  String get noHouseholdBody => 'Oder tritt einem per Einladungslink bei.';

  @override
  String get retry => 'Erneut versuchen';

  @override
  String get errorGeneric => 'Etwas ist schiefgelaufen.';

  @override
  String get errorForbidden => 'Deine Rolle erlaubt das nicht mehr.';

  @override
  String get errorSafetyLimit => 'Das ist länger als das Limit dieser Pumpe.';

  @override
  String get errorHubOffline => 'Der Hub ist offline.';

  @override
  String get errorTooLate => 'Das Gerät hat das bereits übernommen.';

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
  String get deviceSleeping => 'Schläft';

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
  String batteryValue(int percent) {
    return 'Akku $percent %';
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
      'Geräte schlafen zwischen den Messungen. Das Gießen startet beim nächsten Aufwachen.';

  @override
  String pumpLimit(int seconds) {
    return 'Pumpenlimit: $seconds s';
  }

  @override
  String get waterQueued => 'Gießen eingeplant';

  @override
  String get waterQueuedHubOffline =>
      'Eingeplant. Wird ausgeführt, sobald der Hub wieder online ist.';

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
  String commandQueued(String time) {
    return 'Eingeplant · Gerät erwartet ~$time';
  }

  @override
  String get commandDelivered => 'Zugestellt';

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
  String get originCloudRule => 'Regel (Cloud)';

  @override
  String get originHubRule => 'Regel (Hub)';

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
  String get deleteRule => 'Regel löschen';

  @override
  String ruleSummary(int percent, int seconds, int hours) {
    return 'Unter $percent % → $seconds s gießen, höchstens alle $hours h';
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
  String signalValue(int rssi) {
    return 'Signal $rssi dBm';
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
  String get wakeInterval => 'Aufwachintervall';

  @override
  String everyMinutes(int minutes) {
    return 'alle $minutes Min.';
  }

  @override
  String get nextExpected => 'Nächstes Aufwachen erwartet';

  @override
  String get slots => 'Steckplätze';

  @override
  String slotLabel(int index) {
    return 'Steckplatz $index';
  }

  @override
  String pinLabel(int pin) {
    return 'GPIO $pin';
  }

  @override
  String get identify => 'Identifizieren';

  @override
  String get reboot => 'Neustart';

  @override
  String get serviceMode => 'Servicemodus';

  @override
  String get deviceActionSent =>
      'Gesendet. Das Gerät reagiert beim nächsten Aufwachen.';

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
  String get household => 'Haushalt';

  @override
  String get timezone => 'Zeitzone';

  @override
  String get yourRole => 'Deine Rolle';

  @override
  String get demoSection => 'Demo';

  @override
  String get demoRole => 'Demo-Rolle in diesem Haushalt';

  @override
  String get demoRoleHint => 'Nur im Dev-Build ohne Backend.';

  @override
  String get notAllowed => 'Deine Rolle erlaubt das nicht.';

  @override
  String get battery => 'Akku';

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
  String get hubTitle => 'Hub';

  @override
  String get hubNoneTitle => 'Gießen auch ohne Internet';

  @override
  String get hubNoneBody =>
      'Ein Hub ist ein kleiner Rechner zu Hause, etwa ein Raspberry Pi, der deine Gießregeln lokal ausführt. Starte die Hub-Software und gib den angezeigten Code ein.';

  @override
  String get hubAdd => 'Hub hinzufügen';

  @override
  String get hubCodeLabel => 'Code vom Hub';

  @override
  String get hubCodeInvalid => 'Gib den 8-stelligen Code ein, etwa K7QM-2XPA.';

  @override
  String get hubClaimNote =>
      'Nach dem Hinzufügen musst du jedes Gerät dieses Haushalts neu mit dem Hub koppeln.';

  @override
  String get hubAdded => 'Hub hinzugefügt. Warte auf die Verbindung.';

  @override
  String get hubEnrolling => 'Warte auf die Verbindung des Hubs';

  @override
  String hubOfflineSince(String time) {
    return 'Offline seit $time';
  }

  @override
  String get hubInSync => 'Einstellungen aktuell';

  @override
  String get hubSyncing => 'Einstellungen werden übertragen';

  @override
  String get hubAgentVersion => 'Agent-Version';

  @override
  String hubUpdateAvailable(String version) {
    return 'Update verfügbar: $version';
  }

  @override
  String get hubUpdateHint =>
      'Auf dem Hub ausführen: docker compose pull && docker compose up -d';

  @override
  String get hubQueue => 'Wartende Nachrichten an die Cloud';

  @override
  String get hubClock => 'Uhrzeit';

  @override
  String get hubClockOk => 'Synchron';

  @override
  String get hubClockBad => 'Nicht synchron: kein automatisches Gießen';

  @override
  String get hubLastReport => 'Letzte Meldung';

  @override
  String get hubLanAddress => 'LAN-Adresse';

  @override
  String get hubLanHint =>
      'Geräte verbinden sich mit dieser Adresse. Überschreibe sie, wenn der Hub mehrere Netzwerkschnittstellen hat.';

  @override
  String get hubLanReported => 'Vom Hub gemeldet';

  @override
  String get hubLanOverridden => 'Manuell festgelegt';

  @override
  String get hubLanUnknown => 'Noch nicht gemeldet';

  @override
  String get hubLanReset => 'Gemeldete Adresse verwenden';

  @override
  String get edit => 'Bearbeiten';

  @override
  String get hubRepairTitle => 'Neu zu koppelnde Geräte';

  @override
  String get hubRepairBody =>
      'Diese Geräte nutzen noch die alte Verbindung. Kopple jedes mit der Handy-App neu, in der Nähe des Geräts.';

  @override
  String get deviceNeedsRepair => 'Neu koppeln';

  @override
  String get hubRemove => 'Hub entfernen';

  @override
  String get hubRemoveTitle => 'Hub entfernen?';

  @override
  String get hubRemoveBody =>
      'Alle Geräte dieses Haushalts melden sich erst wieder, wenn du sie neu mit der Cloud koppelst. Der Verlauf bleibt erhalten.';

  @override
  String get hubRemoved => 'Hub entfernt';

  @override
  String get hubNone => 'Kein Hub';

  @override
  String get errorInvalidCode =>
      'Der Code ist ungültig oder abgelaufen. Der Hub zeigt einen neuen an.';

  @override
  String get errorHubExists => 'Dieser Haushalt hat bereits einen Hub.';

  @override
  String get errorReauth => 'Melde dich erneut an, um das zu tun.';
}
