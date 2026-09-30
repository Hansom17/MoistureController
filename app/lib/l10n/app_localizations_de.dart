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
  String gatewayOfflineBanner(String time) {
    return 'Gateway offline seit $time. Gießen wird ausgeführt, sobald es wieder da ist.';
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
  String get errorGatewayOffline => 'Das Gateway ist offline.';

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
  String get waterQueuedGatewayOffline =>
      'Eingeplant. Wird ausgeführt, sobald das Gateway wieder online ist.';

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
  String get originRule => 'Regel';

  @override
  String get originLocal => 'Am Gateway';

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
  String get gatewayTitle => 'Gateway';

  @override
  String get gatewayNoneTitle => 'Pflanzen verbinden';

  @override
  String get gatewayNoneBody =>
      'Pflanzengeräte sprechen mit einem Gateway: einem kleinen Rechner zu Hause, etwa einem Raspberry Pi, der deine Gießregeln auch ohne Internet ausführt. Starte die Gateway-Software und gib den angezeigten Code ein.';

  @override
  String get gatewayAdd => 'Gateway hinzufügen';

  @override
  String get gatewayCodeLabel => 'Code vom Gateway';

  @override
  String get gatewayCodeInvalid =>
      'Gib den 8-stelligen Code ein, etwa K7QM-2XPA.';

  @override
  String get gatewayClaimNote =>
      'Bisher gekoppelte Geräte musst du neu mit dem neuen Gateway koppeln.';

  @override
  String get gatewayAdded => 'Gateway hinzugefügt. Warte auf die Verbindung.';

  @override
  String get gatewayEnrolling => 'Warte auf die Verbindung des Gateways';

  @override
  String gatewayOfflineSince(String time) {
    return 'Offline seit $time';
  }

  @override
  String get gatewayInSync => 'Einstellungen aktuell';

  @override
  String get gatewaySyncing => 'Einstellungen werden übertragen';

  @override
  String get gatewayVersion => 'Version';

  @override
  String get gatewayAdapters => 'Gerätetypen';

  @override
  String gatewayUpdateAvailable(String version) {
    return 'Update verfügbar: $version';
  }

  @override
  String get gatewayUpdateHint =>
      'Auf dem Gateway ausführen: docker compose pull && docker compose up -d';

  @override
  String get gatewayOutbox => 'Noch nicht hochgeladene Nachrichten';

  @override
  String get gatewayClock => 'Uhrzeit';

  @override
  String get gatewayClockOk => 'Synchron';

  @override
  String get gatewayClockBad => 'Nicht synchron: kein automatisches Gießen';

  @override
  String get gatewayLastReport => 'Letzte Meldung';

  @override
  String get gatewayLanAddress => 'LAN-Adresse';

  @override
  String get gatewayLanHint =>
      'Geräte verbinden sich mit dieser Adresse. Überschreibe sie, wenn das Gateway mehrere Netzwerkschnittstellen hat.';

  @override
  String get gatewayLanReported => 'Vom Gateway gemeldet';

  @override
  String get gatewayLanOverridden => 'Manuell festgelegt';

  @override
  String get gatewayLanUnknown => 'Noch nicht gemeldet';

  @override
  String get gatewayLanReset => 'Gemeldete Adresse verwenden';

  @override
  String get edit => 'Bearbeiten';

  @override
  String get gatewayRepairTitle => 'Neu zu koppelnde Geräte';

  @override
  String get gatewayRepairBody =>
      'Diese Geräte sind nicht mit diesem Gateway gekoppelt. Kopple jedes mit der Handy-App neu, in der Nähe des Geräts.';

  @override
  String get deviceNeedsRepair => 'Neu koppeln';

  @override
  String get gatewayRemove => 'Gateway entfernen';

  @override
  String get gatewayRemoveTitle => 'Gateway entfernen?';

  @override
  String get gatewayRemoveBody =>
      'Seine Geräte melden sich erst wieder, wenn du ein Gateway hinzufügst und sie neu koppelst. Auch automatisches Gießen stoppt. Der Verlauf bleibt erhalten.';

  @override
  String get gatewayRemoved => 'Gateway entfernt';

  @override
  String get gatewayNone => 'Kein Gateway';

  @override
  String get errorInvalidCode =>
      'Der Code ist ungültig oder abgelaufen. Das Gateway zeigt einen neuen an.';

  @override
  String get errorGatewayExists => 'Dieser Haushalt hat bereits ein Gateway.';

  @override
  String get errorNoGateway =>
      'Füge diesem Haushalt zuerst ein Gateway hinzu (Einstellungen → Gateway).';

  @override
  String get errorReauth => 'Melde dich erneut an, um das zu tun.';

  @override
  String get pairAddDevice => 'Gerät hinzufügen';

  @override
  String get pairWebOnly =>
      'Zum Hinzufügen eines Geräts wird Bluetooth gebraucht. Öffne die App auf dem Handy.';

  @override
  String get pairLabelTitle => 'Etikett des Geräts scannen';

  @override
  String get pairLabelBody =>
      'Halte die Kamera auf den QR-Code auf dem Etikett des Pflanzengeräts.';

  @override
  String get pairManualToggle => 'Code von Hand eingeben';

  @override
  String get pairManualName => 'Name auf dem Etikett (MC-XXXX)';

  @override
  String get pairManualCode => 'Code (26 Zeichen)';

  @override
  String get pairLabelInvalid => 'Das ist kein MoistureController-Etikett.';

  @override
  String get pairContinue => 'Weiter';

  @override
  String get pairNameTitle => 'Gib dem Gerät einen Namen';

  @override
  String get pairNameHint => 'Küchenfenster';

  @override
  String get pairStart => 'Kopplung starten';

  @override
  String get pairCreating => 'Gerät wird deinem Haushalt hinzugefügt …';

  @override
  String pairFinding(String name) {
    return 'Suche $name …';
  }

  @override
  String get pairHandshake => 'Sichere Verbindung wird aufgebaut …';

  @override
  String get pairScanning => 'Suche WLAN-Netze …';

  @override
  String get pairWifiTitle => 'WLAN für das Gerät wählen';

  @override
  String get pairWifiBody =>
      'Es muss das Netz sein, in dem dein Gateway hängt.';

  @override
  String get pairSsidLabel => 'Netzwerkname';

  @override
  String get pairPasswordLabel => 'WLAN-Passwort';

  @override
  String get pairConnect => 'Verbinden und testen';

  @override
  String get pairTestingTitle => 'Verbindung wird getestet …';

  @override
  String get pairTestingBody =>
      'Das Gerät meldet sich im WLAN an und kontaktiert dein Gateway. Das dauert bis zu 40 Sekunden.';

  @override
  String get pairTestWifiFailed =>
      'Das Gerät konnte dem WLAN nicht beitreten. Prüfe Name und Passwort.';

  @override
  String pairTestMqttFailed(String detail) {
    return 'Das Gerät war im WLAN, konnte das Gateway aber nicht erreichen ($detail).';
  }

  @override
  String get pairFinishing => 'Fast fertig …';

  @override
  String get pairWaitingOnline => 'Warte darauf, dass sich das Gerät meldet …';

  @override
  String get pairDoneTitle => 'Gerät hinzugefügt';

  @override
  String pairDoneBody(String name) {
    return '$name ist verbunden.';
  }

  @override
  String get pairDoneSlow =>
      'Das Gerät wurde hinzugefügt, hat sich aber noch nicht gemeldet. Es sollte in ein paar Minuten online erscheinen.';

  @override
  String get pairOpenDevice => 'Gerät öffnen';

  @override
  String get pairFailNoGateway =>
      'Füge diesem Haushalt zuerst ein Gateway hinzu (Einstellungen → Gateway).';

  @override
  String get pairFailGatewayOffline =>
      'Das Gateway ist offline. Bring es zuerst online.';

  @override
  String get pairFailNotFound =>
      'Kein Gerät gefunden. Ein neues Gerät meldet sich von selbst; ein bereits gekoppeltes braucht 3 Sekunden gedrückte BOOT-Taste.';

  @override
  String get pairFailWrongCode =>
      'Falsches Gerät oder falscher Code. Das Gerät wurde wieder entfernt.';

  @override
  String get pairFailConnection => 'Die Verbindung zum Gerät ist abgebrochen.';

  @override
  String get pairFailBluetoothOff =>
      'Bluetooth ist aus. Schalte es ein und versuche es erneut.';

  @override
  String get pairFailBluetoothDenied =>
      'Die App braucht die Erlaubnis, Bluetooth zu nutzen. Erlaube sie in den Systemeinstellungen.';

  @override
  String get pairFailUnsupported =>
      'Dieses Gerät kann nicht per Bluetooth koppeln. Nutze die Mobil-App.';

  @override
  String get pairFailOther => 'Etwas ist schiefgelaufen.';

  @override
  String get pairTryAgain => 'Erneut versuchen';

  @override
  String get pairClose => 'Schließen';

  @override
  String get pairCancelTitle => 'Kopplung abbrechen?';

  @override
  String get pairCancelBody =>
      'Das Gerät wird wieder aus deinem Haushalt entfernt.';

  @override
  String get pairKeepGoing => 'Weitermachen';
}
