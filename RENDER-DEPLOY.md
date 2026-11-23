# Hamburg Transit Radar – Veröffentlichung auf Render

## Was diese Version enthält
- Docker-Start für den FastAPI-Webserver (nicht den lokalen Windows-/pywebview-Launcher)
- Server-Abhängigkeiten ohne `pywebview`
- Render Blueprint (`render.yaml`) für einen ersten kostenlosen Funktionstest
- `.env` und Python-Cache-Dateien sind absichtlich NICHT enthalten

## Veröffentlichen
1. ZIP entpacken.
2. Den Projektordner in ein privates GitHub-Repository hochladen. `.env` nicht hinzufügen.
3. Bei Render **New + → Blueprint** wählen und das GitHub-Repository verbinden.
4. Render erkennt `render.yaml`. Den Dienst `hamburg-transit-radar` erstellen.
5. Bei Bedarf `GTI_USER` und `GTI_PASS` in Render unter **Environment** als geheime Variablen eintragen. Niemals in GitHub oder ins Frontend schreiben.
6. Nach dem Deploy die Render-URL öffnen. `/api/status` sollte einen JSON-Status liefern; die Haupt-URL zeigt die Karte.

## Wichtig zum kostenlosen Testbetrieb
Der Blueprint nutzt zunächst den kostenlosen Render-Dienst. Dieser kann bei Inaktivität einschlafen und sein lokaler Speicher ist nicht dauerhaft. Nach einem Neustart kann der Fahrplan erneut heruntergeladen werden. Für dauerhaft verfügbaren Betrieb und verlässlichen Dateispeicher später einen kostenpflichtigen Dienst mit Persistent Disk einrichten.

## IONOS einbinden
Wenn die Render-App läuft, in IONOS im Website-Editor einen HTML-/Iframe-Block einfügen und die öffentliche Render-URL als `src` verwenden:

```html
<iframe src="https://DEINE-RENDER-URL" title="Hamburg Transit Radar" style="width:100%;height:850px;border:0" loading="lazy" allowfullscreen></iframe>
```

`DEINE-RENDER-URL` durch die echte Render-Adresse ersetzen. Die App bleibt öffentlich und benötigt keine Anmeldung.

## Daten-/Echtzeit-Hinweis
Die App kann Positionen aus dem Fahrplan schätzen. Echte GPS-Positionen erscheinen nur, wenn ein passender Fahrzeugpositions-Feed verfügbar und konfiguriert ist. Ein GTI-Zugang ist optional und muss separat vom HVV freigeschaltet werden.
