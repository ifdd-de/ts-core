# Changelog

The version scheme follows the other IFDD repositories: `YY.MM.N`.

## [Unreleased]

First version (26.10.2).

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
