(ifdd-ts-core-index)=
# ifdd-ts-core

The shared runtime of the IFDD time series API: everything that is the same
in every instance generated from the template `ifdd-de/ts-api`. It checks
the access tokens and store patterns of the callers, checks every sample
against the vocabulary of its property in the type service, reads and writes
samples in VictoriaMetrics, and serves the documentation pages `/docs` and
`/redoc`. An instance contributes only its settings.

| | |
|---|---|
| Distribution | `ifdd-ts-core` |
| Import | `ifdd.ts.core` (`ifdd` and `ifdd.ts` are namespace packages) |
| Python | 3.11 or later |
| Time series database | VictoriaMetrics (checked with v1.153.0) |
| License | BSD-3-Clause; Swagger UI (Apache-2.0) and ReDoc (MIT) are included |

## How an instance uses it

```python
from ifdd.ts.core import create_app
from app.settings import settings      # a subclass of CoreSettings

app = create_app(settings)
```

The container starts the factory directly
(`uvicorn --factory ifdd.ts.core:create_app`). Every endpoint is below the
path prefix `IFDD_TS_API_PATH` (default `/tsapi`). The operation of an
instance is described in the chapter of the instance
({ref}`ifdd-ts-api-index`).

## Concepts in short

- **Stores.** A store is a named part of the one VictoriaMetrics instance;
  every sample carries the label `ifdd_store`. The API sets it on every write
  and requires it on every read, with VictoriaMetrics' parameter
  `extra_label`. Store names are written like DNS names.
- **Access.** Callers are services with tokens of the client credentials
  grant. The role `ifdd_ts_ro` reads, `ifdd_ts_rw` writes; a role with a dot
  is a store pattern and opens that store and every store below it. A
  foreign store answers 403.
- **Series.** A series is named by `name`, `ifdd_id`, `ifdd_property` and
  `ifdd_unit` (the series contract of `ifdd-ts`); no other labels.
- **Checks.** The property must be defined in its vocabulary in the type
  service; the unit must be one of its applicable units and the value within
  its bounds, where the vocabulary names them.
- **Appending only.** There is no PUT: VictoriaMetrics cannot replace a
  sample. With deduplication on (as in `ifdd-ts`), two samples of the same
  series and time leave the larger value.

The [README of the repository](https://github.com/ifdd-de/ts-core) explains
each of them in detail.

## Chapters

```{toctree}
:maxdepth: 2

api-http
api-python
```
