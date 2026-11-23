# Hamburg Transit Radar

Live-Karte (Leaflet/OpenStreetMap) für Busse, U-Bahnen und S-Bahnen im HVV-Gebiet. Backend: Python/FastAPI.

## Installation (Windows)
Das Programm öffnet ein eigenes Fenster (pywebview, nutzt Edge WebView2). Fehler stehen im Fenster und in `log.txt`. Fallback ohne pywebview: Browser mit zufälligem freien Port.
1. Python 3.10+ von python.org installieren (Haken bei „Add to PATH“).
2. Ordner entpacken, `start.bat` doppelklicken. Beim ersten Start werden Pakete installiert und der HVV-Fahrplan (GTFS) geladen – das dauert einige Minuten (Statusmeldung im Browser).
3. Browser öffnet http://localhost:8000. Am Handy im selben WLAN: in `start.bat` `--host 0.0.0.0` setzen und `http://<PC-IP>:8000` öffnen.

## Datenquellen – ehrlicher Stand
- **Fahrplan (GTFS)**: offene HVV-Daten im Transparenzportal Hamburg (Lizenz dl-de/by-2-0). Die Download-URL ändert sich mit jedem Fahrplan. Neue URL in `.env` eintragen und `data\gtfs.zip` löschen – oder die ZIP manuell nach `data\gtfs.zip` legen.
- **Standard-Modus**: alle Positionen werden aus dem Fahrplan **geschätzt** (Kennzeichnung „FAHRPLAN – geschätzt“): Zeit + Haltezeiten, lineare Interpolation zwischen Haltestellen (entlang `shapes.txt`, falls vorhanden).
- **Echte GPS-Positionen**: Ich habe keinen öffentlichen, offiziellen GTFS-Realtime-Feed für HVV-Fahrzeugpositionen gefunden. Gibt es einen, trage die Protobuf-URL als `GTFS_RT_VEHICLES_URL` in `.env` ein: Fahrzeuge mit passender `trip_id` werden dann als „LIVE GPS“ angezeigt. Der Status „LIVE – berechnet“ und echte Verspätungen (TripUpdates) sind noch nicht umgesetzt – Verspätung zeigt „k. A.“.
- **HVV-Switch-App / HVV-GTI-API**: Die offizielle GTI-API (Abfahrten, Verspätungen) erfordert eine Registrierung beim HVV. Private App-Schnittstellen werden bewusst nicht genutzt. Zugangsdaten gehören nur ins Backend (`.env`), nie ins Frontend.

## Quellen-Abgleich (Priorität je Fahrzeug)
1. **LIVE GPS** – echte Position aus einem GTFS-RT-Feed (VehiclePositions).
2. **LIVE – berechnet** – GTI `getVehicleMap` (Linie komplett) oder Fahrplanfahrt mit Echtzeit-Verspätung aus einem GTFS-RT-Feed (TripUpdates).
3. **FAHRPLAN – geschätzt** – reiner Fahrplan.
Standardmäßig wird der kostenlose gtfs.de-Feed (https://realtime.gtfs.de/realtime-free.pb, CC BY-SA, „Teile Deutschlands“) abgefragt. Ob er Hamburger Fahrten enthält und zu den HVV-`trip_id`s passt, siehst du in der Seitenleiste („Verspät. x/y zugeordnet“). Weitere Feeds: `GTFS_RT_URLS` in `.env`.
Nicht genutzt: inoffizielle HAFAS-/App-Schnittstellen (nutzen fremde App-Zugangsschlüssel).

## HVV-GTI-Zugang (Echtzeit & Verspätungen)
1. Zugang beim HVV/Hochbahn per Mail beantragen (siehe Chat-Vorlage): Name, Kontakt, kurze Projektbeschreibung, Zweck (privat/nicht kommerziell), Hinweis auf `getVehicleMap` und `departureList`.
2. Du erhältst Benutzername und Passwort. Beides in `.env` bei `GTI_USER` und `GTI_PASS` eintragen (nie ins Frontend, nie weitergeben).
3. Neu starten. Linien mit GTI-Daten erscheinen als „LIVE – berechnet“ mit Verspätung, alle anderen bleiben „FAHRPLAN – geschätzt“.
Limits laut GTI-Handbuch: mehr als ca. 1 Aufruf/s im Schnitt führt zur Sperre (das Programm nutzt 1 Aufruf je 10 s). Unter `/api/gti/raw` siehst du Rohdaten zur Diagnose.
**Hinweis:** Die GTI-Anbindung ist nach Handbuch umgesetzt, aber ohne Zugangsdaten ungetestet.

## Streckengeometrie
Liegt `shapes.txt` im GTFS bei, fahren Fahrzeuge entlang der Gleis-/Straßenlinie, sonst auf der Luftlinie zwischen Haltestellen.

## Nicht enthalten (Ausbaustufen)
Störungs-Hervorhebung, Fähren-Icons.
