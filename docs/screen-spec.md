# HMI-Spezifikation, Protokollversion 1

## Zielgerät

- vom Display gemeldeter Typ: `TJC4827X243_011C`
- Herstellerfamilie: TJC/USART HMI
- native Panelauflösung laut Referenz-TFT-Header: 480 × 272 Pixel
- Einbau und Bedienoberfläche: um 90° gedrehtes Hochformat
- logische Layoutfläche: 272 × 480 Pixel
- UART: 115200 Baud, 8N1
- Nextion-kompatible Befehle mit `FF FF FF` als Abschluss

Die UART-Identifikation liefert:

```text
comok 2,1073-0,TJC4827X243_011C,165,10201,2FB43401475FC35B,16777216-0
```

Das Projekt wird mit TJC `USART HMI` erstellt. Die offizielle Downloadseite
führt aktuell die Editorversion 1.68.1.

Das HMI wird als neues Projekt angelegt. Grafiken und Symbole werden nicht aus
KlipperScreen kopiert; lediglich Informationshierarchie, dunkles Erscheinungsbild
und Bedienlogik dienen als gestalterische Referenz.

Die native Auflösung allein legt die Ausrichtung nicht fest. Vor dem ersten
Kompilieren wird im HMI-Editor geprüft, ob der Zieltyp die Drehung als
Projekteinstellung oder als Geräteattribut speichert. Alle Koordinaten und
Entwürfe dieses Projekts verwenden unabhängig davon 272 × 480 im Hochformat.

## Gestaltungsraster

- Hintergrund: `#13171D`
- Flächen: `#20262E`
- Primärfarbe: `#E9A23B`
- Text: `#F4F6F8`
- Sekundärtext: `#A7B0BA`
- Fehler: `#E45858`
- Mindesthöhe berührbarer Elemente: 48 px
- Statusleiste oben: 40 px
- Seitenrand: 12 px
- Standardabstand: 8 px

Die importierten Hintergrundbilder enthalten ausschließlich feste Geometrie
und Symbole. Alle sichtbaren Beschriftungen werden vom UART-Dienst zur Laufzeit
gezeichnet. Dabei ist jeder Text einer Farbrolle (`accent`, `text`, `muted`,
`danger` oder `dark`) zugeordnet. Texte der Rolle `accent` übernehmen deshalb
sofort die ausgewählte Akzentfarbe und werden beim Seitenwechsel neu gezeichnet.

Für jedes Akzentschema besitzt die HMI eine vollständige Seitenvariante. Der
Dienst wählt sie beim Öffnen einer Seite anhand der gespeicherten Akzentfarbe
aus. Dadurch wechseln auch nicht-textuelle Symbole, Pfeile, weiche Farbkacheln,
Primärflächen und abgerundete Rahmen; sie sind nicht mehr an den orangefarbenen
Basisexport gebunden. Zustandsabhängige Markierungen wie Move-Schrittweite,
Dateiquelle, Datei-/WLAN-/Makroauswahl und Verbindungsgrün werden separat zur
Laufzeit gezeichnet.

Datei-, WLAN- und Makrozeilen gehören ebenfalls nicht zum Hintergrund. Der
Dienst zeichnet Fläche und Rahmen nur für tatsächlich vorhandene Einträge und
deaktiviert Touch- sowie Textkomponenten der übrigen Zeilen.

Messwerte sind ebenfalls reine Laufzeitdaten. Solange Klipper nicht verbunden
ist, zeigen Home und Temperatur `–` statt scheinbarer `0`-Messwerte.

## Seiten

| ID | HMI-Name | Zweck |
|---:|---|---|
| 0 | `boot` | Start, Verbindung und Protokollprüfung |
| 1 | `home` | Temperaturen, Druckstatus und Hauptnavigation |
| 2 | `move` | Homing und Achsbewegung |
| 3 | `temperature` | Heizer, Lüfter und Extrusion |
| 4 | `files` | G-Code-Auswahl |
| 5 | `print` | laufender Druck |
| 6 | `tune` | Geschwindigkeit, Fluss und Lüfter |
| 7 | `bed` | Z-Offset, Probe und Bed Mesh |
| 8 | `macros` | Klipper-Makros |
| 9 | `settings` | Netzwerk und System |
| 10 | `wifi` | WLAN-Liste |
| 11 | `wifi_password` | Passworttastatur |
| 12 | `system` | Versionen, IP und Neustartaktionen |
| 13 | `dialog` | Bestätigungen und Fehler |
| 14 | `accent` | Akzentfarbe, Sprache und Tastaturlayout auswählen |

## Komponenten der ersten Ausbaustufe

Die Reihenfolge ist verbindlich, weil das HMI daraus die Komponenten-ID bildet.
Die Touch-Ereignisse müssen beim Loslassen gesendet werden.

### `boot` (Seite 0)

Das Artillery-Symbol wird zur Laufzeit als Vektorgrafik in der gewählten
Akzentfarbe gezeichnet. Der Verbindungstext basiert auf Moonrakers
`klippy_connected`-Status: Während der Abfrage wird „Verbinde mit Klipper …“
angezeigt, anschließend entweder der verbundene oder der getrennte Zustand.


| ID | Name | Typ |
|---:|---|---|
| 1 | `tStatus` | Text |
| 2 | `vaProtocol` | Variable |
| 3 | `vaAccent` | globale Variable |
| 4 | `jProgress` | echter Initialisierungsfortschritt 0–100 |

Die Boot-Seite verwendet das Artillery-Symbol, den Haupttitel `ARTILLERY`,
die Modellzeile `SIDEWINDER X4` und den Untertitel `UART TOUCH INTERFACE`.
Die Bezeichnung `Klipper Screen` wird nicht verwendet, weil der Dienst eine
eigene UART-Oberfläche und keine KlipperScreen-Instanz ist.
Der Fortschrittsbalken ist kein Bestandteil des Hintergrundbildes. Der Dienst
setzt ihn entsprechend der abgeschlossenen Schritte UART, Protokoll,
Druckerstatus und Netzwerk und wechselt erst danach zur Startseite.

### `home` (Seite 1)

| ID | Name | Typ/Aktion |
|---:|---|---|
| 1 | `bMove` | Taste: Bewegen |
| 2 | `bTemperature` | Taste: Temperatur |
| 3 | `bFiles` | Taste: Dateien |
| 4 | `bBed` | Taste: Druckbett |
| 5 | `bMacros` | Taste: Makros |
| 6 | `bSettings` | Taste: Einstellungen |
| 7 | `bEmergency` | Taste: Not-Aus |
| – | `tNozzle` | Text |
| – | `tBed` | Text |
| – | `tState` | Text |
| – | `tFile` | Text |
| – | `jProgress` | Fortschritt 0–100 |
| – | `tConnection` | Text |
| – | `tWifi` | Text |

### `move` (Seite 2)

| ID | Name | Typ/Aktion |
|---:|---|---|
| 1 | `bBack` | zurück zur Startseite |
| 2 | `bHomeAll` | alle Achsen homen |
| 3–5 | `bHomeX`–`bHomeZ` | einzelne Achse homen |
| 6/7 | `bXMinus`/`bXPlus` | X relativ bewegen |
| 8/9 | `bYMinus`/`bYPlus` | Y relativ bewegen |
| 10/11 | `bZMinus`/`bZPlus` | Z relativ bewegen |
| 12 | `bStep01` | Schrittweite 0,1 mm |
| 13 | `bStep1` | Schrittweite 1,0 mm |
| 14 | `bStep10` | Schrittweite 10 mm |
| – | `tX`/`tY`/`tZ` | aktuelle Werkzeugkopfposition |
| – | `tStep` | aktive Schrittweite |
| – | `tStatus` | Bewegungs- oder Fehlermeldung |
| 20 | `tForce` | Taste und Status `FORCE MOVE - AUS/AKTIV` |

Achsen werden über relative `G0`-Bewegungen verfahren; X/Y verwenden
6000 mm/min, Z 600 mm/min. Während eines laufenden oder pausierten Drucks
sind Homing und manuelles Verfahren gesperrt.

Force Move verwendet Klippers `FORCE_MOVE` direkt auf `stepper_x`,
`stepper_y` oder `stepper_z`. Die Aktivierung erfordert eine ausdrückliche
Bestätigung, setzt die Schrittweite auf 0,1 mm und begrenzt erzwungene
Einzelbewegungen auf maximal 1 mm. Der Modus wird beim Homing und beim
Verlassen der Seite automatisch deaktiviert; danach ist ein vollständiges
Homing erforderlich. Beim X4 hängen beide Z-Motoren gemeinsam am Treiber von
`stepper_z` und werden deshalb synchron bewegt. Die Klipper-Konfiguration muss
`[force_move]` mit `enable_force_move: True` enthalten.

### `temperature` (Seite 3)

| ID | Name | Typ/Aktion |
|---:|---|---|
| 1 | `bBack` | zurück zur Startseite |
| 2/3 | `bNozzleMinus`/`bNozzlePlus` | Düsen-Ziel um 5 °C senken/erhöhen |
| 4/5 | `bBedMinus`/`bBedPlus` | Bett-Ziel um 5 °C senken/erhöhen |
| 6/7 | `bFanMinus`/`bFanPlus` | Bauteillüfter um 10 % senken/erhöhen |
| 8 | `bOff` | beide Heizer und Bauteillüfter ausschalten |
| 9 | `bPLA` | Schnellprofil 200/60 °C |
| 10 | `bPETG` | Schnellprofil 235/75 °C |
| 11 | `bABS` | Schnellprofil 250/100 °C |
| 12 | `tNozzle` | aktuelle und gewünschte Düsentemperatur |
| 13 | `tBed` | aktuelle und gewünschte Betttemperatur |
| 14 | `tFan` | aktuelle Lüfterleistung |
| 15 | `tStatus` | Bestätigung oder Fehlermeldung |

Die Software begrenzt die Düse auf 300 °C, das Bett auf 110 °C und den
Bauteillüfter auf 0–100 %. Temperaturziele werden mit
`SET_HEATER_TEMPERATURE` gesetzt; der Lüfter verwendet `M106` beziehungsweise
`M107`. Die Schnellprofile ändern den Lüfter nicht, während `AUS` alle drei
Ausgänge abschaltet.

### `print` (Seite 5)

| ID | Name | Typ/Aktion |
|---:|---|---|
| 1 | `bBack` | zurück zur Startseite |
| 2 | `bPause` | laufenden Druck pausieren oder fortsetzen |
| 3 | `bCancel` | Druckabbruch mit Sicherheitsdialog |
| 4 | `bTemp` | Temperaturseite öffnen |
| 5 | `tFile` | Dateiname |
| 6 | `tState` | Druckstatus |
| 7 | `jProgress` | Fortschritt 0–100 |
| 8 | `tProgress` | Fortschritt in Prozent |
| 9 | `tElapsed` | bisherige Druckzeit |
| 10 | `tNozzle` | Düsen-Ist- und Zieltemperatur |
| 11 | `tBed` | Bett-Ist- und Zieltemperatur |
| 12 | `tStatus` | Bedien- oder Fehlermeldung |

Pause, Fortsetzen und Abbruch verwenden Moonrakers offizielle
`/printer/print/*`-Endpunkte. Der Abbruch wird erst nach Bestätigung im
Dialog ausgeführt.

### `tune` (Seite 6)

Die Seite stellt Geschwindigkeit (50–200 %), Materialfluss (50–150 %) und
Bauteillüfter (0–100 %) während des Drucks ein. Die IDs 2–7 sind Minus/Plus,
ID 8 setzt Geschwindigkeit und Fluss auf 100 % zurück; `tSpeed`, `tFlow`,
`tFan` und `tStatus` sind Live-Texte.

### `bed` (Seite 7)

Die Seite zeigt Z-Position, G-Code-Z-Offset und den letzten Probe-Zustand.
Sie bietet Z-Homing, `PROBE`, Mesh-Kalibrierung, Laden/Löschen des Default-
Meshs sowie Z-Offset-Schritte von 0,01 mm. `SAVE_CONFIG` erfordert eine
Bestätigung, da Klipper dabei neu startet.

### `macros` (Seite 8)

Moonrakers Objektliste liefert die vorhandenen `gcode_macro`-Namen. Je sechs
Makros werden seitenweise angezeigt, zuerst ausgewählt und anschließend über
eine separate Schaltfläche ausgeführt.

### `settings` (Seite 9)

| ID | Name | Typ/Aktion |
|---:|---|---|
| 1 | `bWifi` | Taste: WLAN |
| 2 | `bSystem` | Taste: System |
| 3 | `bAccent` | Taste: Akzentfarbe |
| 9 | `bBack` | Taste: Zurück |
| – | `tWifiI` | WLAN-IP-Adresse oder `–` |
| – | `tLanIP` | LAN-IP-Adresse oder `–` |
| – | `tAccen` | Name der ausgewählten Akzentfarbe |

### `files` (Seite 4)

| ID | Name | Typ/Aktion |
|---:|---|---|
| 1 | `bBack` | im Ordner eine Ebene höher, am Wurzelpunkt zur Startseite |
| 2 | `bInternal` | Quelle `virtual_sdcard` |
| 3 | `bUsb` | Quelle USB-Datenträger |
| 4 | `bPrevious` | vorherige Seite |
| 5 | `bNext` | nächste Seite |
| 6 | `bUp` | eine Ordnerebene höher |
| 7 | `bRefresh` | Quellen und Dateien neu einlesen |
| 10–14 | `bRow0`–`bRow4` | Ordner öffnen oder Datei auswählen |
| 15 | `bPrint` | ausgewählte Datei drucken |
| 18/19 | `tName0`/`tMeta0` | anklickbarer Inhalt von Zeile 1 |
| 20/22 | `tName1`/`tMeta1` | anklickbarer Inhalt von Zeile 2 |
| 21/25 | `tName2`/`tMeta2` | anklickbarer Inhalt von Zeile 3 |
| 26/27 | `n3x`/`tMeta3` | anklickbarer Inhalt von Zeile 4 |
| 23/28 | `tName4`/`tMeta4` | anklickbarer Inhalt von Zeile 5 |
| 29 | `bSort` | Sortierreihenfolge weiterschalten |
| 30 | `tSort` | sichtbare, ebenfalls anklickbare Sortierbeschriftung |
| – | `tSource` | aktive Quelle |
| – | `tPath` | aktueller Pfad |
| – | `tName0`–`tName2`, `n3x`, `tName4` | Ordner- oder Dateiname |
| – | `tMeta0`–`tMeta4` | Typ oder Dateigröße |
| – | `tStatus` | Auswahl-, Kopier- und Fehlermeldungen |

Die Sortierung startet mit `Neu–Alt` und wechselt zyklisch zu `Alt–Neu`,
`A–Z`, `Z–A` und zurück zu `Neu–Alt`. Ordner bleiben unabhängig von der
gewählten Reihenfolge vor den Dateien.

Die interne Quelle wird über Moonrakers Verzeichnis-API aus dem in
`[virtual_sdcard]` eingetragenen `gcodes`-Root gelesen. USB-Datenträger werden
schreibgeschützt betrachtet und unter `/media/artillery/<Gerät>` angeboten.
Vor dem Druck wird eine ausgewählte USB-G-Code-Datei atomar nach
`~/printer_data/gcodes/.artillery-usb/` kopiert. Anschließend startet der Dienst
den Druck über Moonraker mit einem Pfad relativ zum `gcodes`-Root. Dadurch liest
Klipper niemals direkt von einem während des Drucks entfernbaren Datenträger.

### `wifi` (Seite 10)

Die verbundene WLAN-Karte oberhalb der Liste ist keine Hintergrundgrafik. Sie
wird nur gezeichnet, wenn NetworkManager gleichzeitig eine WLAN-SSID und eine
WLAN-IP-Adresse meldet; bei LAN-only oder getrenntem WLAN bleibt der Bereich
vollständig leer.

| ID | Name | Typ/Aktion |
|---:|---|---|
| 1 | `bScan` | Taste: Neu suchen |
| 2 | `bPrevious` | Taste: vorherige Seite |
| 3 | `bNext` | Taste: nächste Seite |
| 9 | `bBack` | Taste: Zurück |
| 10–14 | `bRow0`–`bRow4` | WLAN auswählen |
| – | `tSSID0`–`tSSID4` | SSID |
| – | `tMeta0`–`tMeta4` | Signal/Sicherheit |
| – | `tStatus` | Statusmeldung |

### `wifi_password` (Seite 11)

| ID | Name | Typ/Aktion |
|---:|---|---|
| 1 | `bConnect` | Taste: Verbinden |
| 2 | `bCancel` | Taste: Abbrechen |
| 3 | `bBack` | Taste: zurück zur WLAN-Liste |
| 4–13 | `bKey1`–`bKey0` | Ziffern 1–0 |
| 14–39 | `bKeyQ`–`bKeyM` | Buchstaben gemäß gewähltem Layout |
| 40 | `bShift` | `ABC` → `abc` → Sonderzeichen umschalten |
| 41 | `bDelete` | letztes Zeichen löschen |
| – | `tSSID` | ausgewähltes WLAN |
| – | `tPass` | maskierte Passworteingabe |
| – | `tStatus` | Statusmeldung |
| – | `tCase` | `ABC`, `abc` oder `?#` |

Die auswählbaren Tastaturlayouts sind Deutsch/QWERTZ, Englisch/QWERTY und
Französisch/AZERTY. Der dritte Tastaturmodus enthält die gebräuchlichen druckbaren ASCII-
Sonderzeichen einschließlich Leerzeichen. Das Passwort bleibt ausschließlich
im Arbeitsspeicher des Dienstes und wird
maskiert als `tPass` angezeigt. Es wird weder protokolliert noch als
Kommandozeilenargument an NetworkManager übergeben.

### `system` (Seite 12)

| ID | Name | Typ/Aktion |
|---:|---|---|
| 1 | `bBack` | zurück zu Einstellungen |
| 2 | `bKlipper` | Klipper-Neustart anfordern |
| 3 | `bFirmware` | Firmware-Neustart anfordern |
| 4 | `bReboot` | CB2-Neustart anfordern |
| 5 | `bShutdown` | CB2 herunterfahren |
| 11 | `bUpdateCheck` | Update-Status neu abrufen |
| 12 | `bUpdateAll` | alle verfügbaren Updates installieren |
| – | `tHost` | Hostname |
| – | `tKlipper` | Klipper-Version |
| – | `tMoon` | Moonraker-Version |
| – | `tNetwork` | LAN- und WLAN-Adresse |
| – | `tStatus` | Distribution oder Fehlermeldung |

Neustart, Herunterfahren und Updates werden über die offiziellen Moonraker-
Endpunkte ausgeführt. Die manuelle Update-Prüfung verwendet
`/machine/update/refresh`; die Installation nutzt ab API 1.5
`/machine/update/upgrade`. CB2-Neustart, Herunterfahren, Update-Prüfung und
Installation sind während eines laufenden oder pausierten Drucks gesperrt.
Neustart, Herunterfahren und Update-Installation erfordern die
Dialogbestätigung.

### `dialog` (Seite 13)

| ID | Name | Typ/Aktion |
|---:|---|---|
| 1 | `bCancel` | Aktion abbrechen |
| 2 | `bConfirm` | vorgemerkte Aktion ausführen |
| – | `tTitle` | Titel der Bestätigung |
| – | `tMessage` | Erläuterung oder Ergebnis |

### `accent` (Seite 14)

| ID | Name | Typ/Aktion |
|---:|---|---|
| 1 | `bBack` | Taste: Zurück |
| 10 | `bOrange` | Orange auswählen |
| 11 | `bBlue` | Blau auswählen |
| 12 | `bGreen` | Grün auswählen |
| 13 | `bPurple` | Violett auswählen |
| 14 | `bRed` | Rot auswählen |
| 17 | `bLanguage` | Sprache Deutsch/Englisch weiterschalten |
| 18 | `bKeyboard` | QWERTZ/QWERTY/AZERTY weiterschalten |
| – | `tCurrent` | Name der aktuellen Auswahl |
| – | `vaSelected` | Index 0–4 für Auswahlmarkierung |

`boot.vaAccent` ist eine numerische Variable mit globalem Gültigkeitsbereich.
Der UART-Dienst verwendet ihren RGB565-Wert beim Zeichnen aller Texte mit der
Farbrolle `accent`. Akzentfarbe, Sprache und Tastaturlayout werden versioniert
unter `printer_data/config/artillery-screen.json` gespeichert. Die statischen
Oberflächentexte und Laufzeitmeldungen stammen aus zentralen Sprachkatalogen;
ein Sprachwechsel lädt die aktuelle Seite neu.
