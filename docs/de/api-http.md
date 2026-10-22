(ifdd-ts-core-api-http)=
# HTTP-API

Die HTTP-API, wie das OpenAPI-Dokument sie beschreibt: jeder Endpunkt mit
Parametern, Antworten, Fehlercodes und Beispielen. Dasselbe Dokument ist in
einer laufenden Instanz unter `/tsapi/docs` (Swagger UI) und `/tsapi/redoc`
zu sehen. Seine Pfade gelten relativ zum Server `/tsapi` (dem Pfadpräfix der
Instanz).

Die Seite liest das Dokument aus `openapi.json` daneben; die Datei liegt
nicht im Repository. Beim Bau der Doku exportieren:

```bash
python -c "import json; from ifdd.ts.core.app import openapi_document; json.dump(openapi_document(), open('openapi.json', 'w'))"
```

```{eval-rst}
.. openapi:: openapi.json
   :examples:
```
