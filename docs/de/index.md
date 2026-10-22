(ifdd-ts-core-index)=
# ifdd-ts-core

Die gemeinsame Laufzeit der IFDD-Zeitreihen-API: alles, was in jeder aus dem
Template `ifdd-de/ts-api` erzeugten Instanz gleich ist. Sie prüft die
Access-Tokens und Store-Muster der Aufrufer, prüft jedes Sample gegen das
Vokabular seiner Eigenschaft im type-Dienst, liest und schreibt Samples in
VictoriaMetrics und liefert die Doku-Seiten `/docs` und `/redoc` aus. Eine
Instanz steuert nur ihre Einstellungen bei.

| | |
|---|---|
| Distribution | `ifdd-ts-core` |
| Import | `ifdd.ts.core` (`ifdd` und `ifdd.ts` sind Namespace-Pakete) |
| Python | 3.11 oder neuer |
| Zeitreihen-Datenbank | VictoriaMetrics (geprüft mit v1.153.0) |
| Lizenz | BSD-3-Clause; Swagger UI (Apache-2.0) und ReDoc (MIT) liegen bei |

## So nutzt eine Instanz das Paket

```python
from ifdd.ts.core import create_app
from app.settings import settings      # eine Unterklasse von CoreSettings

app = create_app(settings)
```

Der Container startet die Fabrik direkt
(`uvicorn --factory ifdd.ts.core:create_app`). Alle Endpunkte liegen unter
dem Pfadpräfix `IFDD_TS_API_PATH` (Standard `/tsapi`). Den Betrieb einer
Instanz beschreibt das Kapitel der Instanz ({ref}`ifdd-ts-api-index`).

## Begriffe in Kürze

- **Stores.** Ein Store ist ein benannter Teil der einen
  VictoriaMetrics-Instanz; jedes Sample trägt das Label `ifdd_store`. Die API
  setzt es bei jedem Schreiben und verlangt es bei jedem Lesen, über den
  VictoriaMetrics-Parameter `extra_label`. Store-Namen sind wie DNS-Namen
  geschrieben.
- **Zugriff.** Aufrufer sind Dienste mit Tokens aus dem Client-Credentials-
  Grant. Die Rolle `ifdd_ts_ro` liest, `ifdd_ts_rw` schreibt; eine Rolle mit
  Punkt ist ein Store-Muster und öffnet diesen Store und alle darunter. Ein
  fremder Store antwortet 403.
- **Reihen.** Eine Reihe heißt nach `name`, `ifdd_id`, `ifdd_property` und
  `ifdd_unit` (Reihenvertrag von `ifdd-ts`); weitere Labels gibt es nicht.
- **Prüfungen.** Die Eigenschaft muss in ihrem Vokabular im type-Dienst
  stehen; die Einheit muss zu ihren zulässigen Einheiten gehören und der
  Wert in ihren Grenzen liegen, wo das Vokabular sie nennt.
- **Nur anhängen.** Es gibt kein PUT: VictoriaMetrics kann ein Sample nicht
  ersetzen. Mit eingeschalteter Deduplizierung (wie in `ifdd-ts`) bleibt von
  zwei Samples derselben Reihe und Zeit der größere Wert.

Die [README des Repositorys](https://github.com/ifdd-de/ts-core) erklärt
jeden Punkt ausführlich.

## Kapitel

```{toctree}
:maxdepth: 2

api-http
api-python
```
