# ifdd-ts-core

Shared runtime of the IFDD time series API. Instances are generated from the
template [`ifdd-de/ts-api`](https://github.com/ifdd-de/ts-api); this package
holds everything they have in common: token and store checks, the check of
samples against the vocabularies of the type service, reading and writing in
VictoriaMetrics, and the documentation pages.

```text
service (client credentials) --HTTPS--> proxy --> ts-api (ifdd-ts-core) --> VictoriaMetrics
                                                        |                         ^
                                                        +--> type service          |
                                                   Grafana (ifdd-ts) reads all ----+
```

- Distribution `ifdd-ts-core`, import `ifdd.ts.core` (`ifdd` and `ifdd.ts`
  are namespace packages). Python 3.11 or later.
- License BSD-3-Clause. Swagger UI and ReDoc are included as third-party files
  (see below).

## Use

```python
from ifdd.ts.core import create_app
from app.settings import settings   # a subclass of ifdd.ts.core.CoreSettings

app = create_app(settings)
```

or `uvicorn --factory ifdd.ts.core:create_app` with the settings in the
environment. Every endpoint is below the path prefix `IFDD_TS_API_PATH`
(default `/tsapi`), so the API can share a host with Grafana behind the
proxy without a rewrite rule.

## Configuration

Environment variables (or `.env`):

| Variable | Default | Meaning |
|---|---|---|
| `IFDD_TS_API_PATH` | `/tsapi` | path prefix of every endpoint; empty serves at the root |
| `IFDD_TS_API_VERSION` | package version | version shown by `/version` and the OpenAPI document |
| `IFDD_TS_API_AUTH_ENABLED` | `true` | `false`: no token is checked, every caller is a development user with both roles and the pattern `IFDD_CONTEXT_ROOT` |
| `IFDD_OIDC_ISSUER` | – | expected `iss`; empty: not checked (warning) |
| `IFDD_OIDC_JWKS_URL` | – | keys of the realm |
| `IFDD_OIDC_TOKEN_URL` | – | only shown in the API description |
| `IFDD_OIDC_JWKS_AUDIENCE` | `ifdd-ts-api` | required `aud`; the client that carries the roles |
| `IFDD_TS_ROLE_READ`, `IFDD_TS_ROLE_WRITE` | `ifdd_ts_ro`, `ifdd_ts_rw` | roles to read and to write |
| `IFDD_CONTEXT_ROOT` | `ifdd.de` | store pattern of the development user |
| `IFDD_TS_VM_URL` | `http://victoriametrics:8428` | VictoriaMetrics |
| `IFDD_TYPE_URL` | `http://type/v1` | type service; every property must be below it |
| `IFDD_TS_MAX_ITEMS` | `10000` | most samples written or read, and most series listed, per request |
| `IFDD_TS_DEFAULT_RANGE_DAYS` | `30` | time range of `/stores` and `/series` without `start` |
| `IFDD_TS_LOOKBACK_DAYS` | `3660` | how far back the latest sample is searched without `max_age` |
| `IFDD_TS_VOCABULARY_CACHE_TTL` | `300` | seconds a vocabulary is kept |
| `IFDD_TOKEN_CACHE_SIZE`, `IFDD_TOKEN_CACHE_TTL` | `1000`, `300` | cache of validated tokens |
| `IFDD_TS_VM_TIMEOUT`, `IFDD_TS_VOCABULARY_TIMEOUT` | `30`, `10` | seconds |

The limit of 10 000 is a starting value, not a measured one.

TLS: calls to the type service (and to the JWKS URL) check certificates
against the system trust store, not against `certifi`; put the CA of the
proxy there, as the ts-api image does.

## Endpoints

All below `IFDD_TS_API_PATH`:

| Method and path | Role | Purpose |
|---|---|---|
| `GET /version` | none | version (health checks) |
| `GET /whoami` | valid token | roles and store patterns read from the token |
| `GET /stores` | read | stores with samples that the caller may read |
| `GET /stores/{store}/series` | read + pattern | series of a store, filtered by labels |
| `GET /stores/{store}/samples` | read + pattern | latest sample of one series at or before `at` |
| `GET /stores/{store}/samples/range` | read + pattern | raw samples of the series of an object in `[start, end]` |
| `POST /stores/{store}/samples` | write + pattern | write one sample |
| `POST /stores/{store}/samples/batch` | write + pattern | write a list of samples (all or nothing on checks) |
| `GET /docs`, `GET /redoc`, `GET /openapi.json` | none | documentation |

Order of checks: token (401), store name (422), role (403), store pattern
(403), body (422), vocabulary (422, or 502 if the type service fails),
VictoriaMetrics (502).

## Stores and access

A store is a named part of the one VictoriaMetrics instance: every sample
carries the label `ifdd_store`. The API passes `extra_label=ifdd_store=<store>`
on every call that reads or writes samples. VictoriaMetrics then sets the
label on every imported sample, overriding one in the body, and adds it as a
filter to every read (checked against v1.153.0). That parameter alone keeps
stores apart; the tests fail without it.

Store names are written like DNS names: at least two labels of lower-case
letters, digits and inner hyphens, e.g. `temperature.ops.example.ifdd.de`.
Any such name is a store; it exists once a sample was written to it.

Callers are services with an access token of the client credentials grant.
The token's audience must be `IFDD_OIDC_JWKS_AUDIENCE`, and its client roles
there decide:

- `ifdd_ts_ro` reads, `ifdd_ts_rw` writes; they apply to every store the
  caller's patterns open;
- a role with a dot is a **store pattern**. It opens the store of that name
  and every store below it, compared at label boundaries
  (`ops.example.ifdd.de` opens `temperature.ops.example.ifdd.de`, not
  `xops.example.ifdd.de`). The root `ifdd.de` opens all.

A foreign store answers 403, not 404. `/stores` leaves out stores the caller
may not read.

**What this does not protect.** Grafana (ifdd-ts) reads VictoriaMetrics
directly and shows the series of every store; containers on the ingest
network write to VictoriaMetrics directly, without any check. Both are
deliberate (see the documentation of ifdd-ts); the API is the way in for
services that should not get either.

## Series and samples

A series is named by four labels, the series contract of ifdd-ts:

| Field | Label | Value |
|---|---|---|
| `name` | `__name__` | metric name, only for people: letters, digits, `_` |
| `ifdd_id` | `ifdd_id` | full IRI of the object in ifdd-be |
| `ifdd_property` | `ifdd_property` | full IRI of the property in the type service |
| `ifdd_unit` | `ifdd_unit` | full IRI of the unit |

No further labels are accepted. A value is a finite number; states are coded
as numbers.

**Times** are ISO 8601 with an offset (`Z`, `+02:00`), at most to the
millisecond, not before 1970. Without offset or with finer precision the API
answers 422 instead of guessing or cutting. Answers are UTC with three
decimals (`2026-10-22T07:15:00.250+00:00`).

**Appending only.** There is no PUT: VictoriaMetrics cannot replace a single
sample. Two samples of the same series and time are both kept, unless
deduplication is on (`-dedup.minScrapeInterval=1ms`, as in ifdd-ts); then
the **larger** value stays, not the later one (checked against v1.153.0).
Sending the same sample twice is therefore harmless.

**Latest sample.** `GET /stores/{store}/samples` needs `ifdd_id` and
`ifdd_property`; if more than one series has them (other name or unit), it
answers 422 and asks for `name` and `ifdd_unit`. It searches back from `at`
in growing windows (one hour, one day, 30 days, 366 days, then
`IFDD_TS_LOOKBACK_DAYS` or `max_age`), so a recent sample costs one small
read.

## Checks against the vocabulary

Before writing, every sample is checked against the vocabulary of its
property in the type service:

1. `ifdd_property` must be below `IFDD_TYPE_URL`. Its namespace is the IRI up
   to the last `/` or `#`; the type service answers the namespace IRI with
   the vocabulary.
2. The vocabulary must define the property as an `rdf:Property`.
3. If the property lists `qudt:applicableUnit`, `ifdd_unit` must be one of
   them.
4. If it has `sh:minInclusive` or `sh:maxInclusive`, the value must lie
   within.

The vocabulary is read with a JSON-LD processor, so prefixes and term names
do not matter; its context must be inline. A vocabulary is kept for
`IFDD_TS_VOCABULARY_CACHE_TTL` seconds; failures are not kept. A batch is
checked completely before anything is written; the 422 answer names every
bad sample by its index.

## Relation to ifdd-be-core

The token check and the documentation pages are copies of the ones in
`ifdd-be-core`, by decision (a shared package would have made this one
depend on PostgreSQL, rdflib and the backend settings). Fixes in one belong
in the other. If a third service needs them, they move into a package of
their own. One difference on purpose: a cached token is checked for expiry
on every use.

## Development

```bash
pip install -e '.[dev]'
pytest
```

`tests/test_vm_integration.py` runs against a real VictoriaMetrics when
`IFDD_TEST_VM_URL` is set; start it with deduplication like ifdd-ts:

```bash
victoria-metrics-prod -storageDataPath=/tmp/vm -httpListenAddr=127.0.0.1:8428 \
    -dedup.minScrapeInterval=1ms -retentionPeriod=10y &
IFDD_TEST_VM_URL=http://127.0.0.1:8428 pytest
```

The CI does the same with the release binary v1.153.0 (SHA-256 checked).

Documentation: `docs/en` and `docs/de` (Sphinx, MyST);
`python tests/check_docs.py . --prefix ifdd-ts-core-` after exporting the
OpenAPI document to `docs/<lang>/openapi.json` (see `api-http.md`).

## Third-party files

`src/ifdd/ts/core/docs_assets/` holds unchanged copies of these npm packages,
the same as in ifdd-be-core; `docs_assets/assets.json` names version,
tarball, npm integrity and the SHA-256 of every file, and
`tests/test_docs_assets.py` checks them.

| Package | Version | License |
|---|---|---|
| `swagger-ui-dist` | 5.33.0 | Apache-2.0 (with `NOTICE`) |
| `redoc` | 2.5.4 | MIT |

The license texts are shipped next to the files and in the wheel; the bundles
contain code under further licenses (see the `*.LICENSE.txt` files).
`docs_assets/ifdd/` is part of this package (BSD-3-Clause). Update them
together with ifdd-be-core, as described in its README.

## AI assistance

Parts of this repository, especially tests, test data and documentation,
were developed or improved with the help of large language models. The
maintainer reviewed and approved every change.

## License

BSD-3-Clause, see [LICENSE](LICENSE).
