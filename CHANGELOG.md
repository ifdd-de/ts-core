# Changelog

The version scheme follows the other IFDD repositories: `YY.MM.N`.

## [26.10.3] - 2026-10-30

- FastAPI 0.162.0: `fastapi>=0.162.0,<0.163.0` (was `>=0.142.2,<0.151.0`).
  FastAPI itself now depends on `opentelemetry-api`.
- Lower bounds raised to the current releases: pydantic 2.14.2,
  pydantic-settings 2.16.2 (was 2.15), cachetools 7.2.7; development: pytest
  9.2.0 (`~=9.2.0`), pytest-asyncio 1.4.1.
- CI: VictoriaMetrics v1.155.0 (was v1.153.0) for the integration tests, the
  version of the ts template.
- Version 26.10.3, also in the example of `/version`.
- Documentation check: Sphinx 9.2.0 (`tests/docs/requirements.txt`).

## [26.10.2] - 2026-10-23

First version.

- Application factory `create_app`; all endpoints below `IFDD_TS_API_PATH`
  (default `/tsapi`).
- `GET /stores`, `GET /stores/{store}/series`, `GET /stores/{store}/samples`
  (latest sample at or before `at`), `GET /stores/{store}/samples/range`,
  `POST /stores/{store}/samples`, `POST /stores/{store}/samples/batch`;
  `GET /version`, `GET /whoami`.
- Stores as label `ifdd_store`, kept apart with VictoriaMetrics'
  `extra_label`; access by the roles `ifdd_ts_ro`/`ifdd_ts_rw` and store
  patterns (client roles with a dot) of the client `ifdd-ts-api`.
- Every sample is checked against the vocabulary of its property in the type
  service (property defined, applicable unit, bounds).
- Times as ISO 8601 with offset, millisecond precision.
- Swagger UI and ReDoc served from the package, without inline script and
  without OAuth2 login (bearer token only).
