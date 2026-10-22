(ifdd-ts-core-api-http)=
# HTTP API

The HTTP API as the OpenAPI document describes it: every endpoint with its
parameters, answers, error codes and examples. The same document is
browsable in a running instance at `/tsapi/docs` (Swagger UI) and
`/tsapi/redoc`. Its paths are relative to the server `/tsapi` (the path
prefix of the instance).

The page reads the document from `openapi.json` next to it, which is not in
the repository. Export it when the documentation is built:

```bash
python -c "import json; from ifdd.ts.core.app import openapi_document; json.dump(openapi_document(), open('openapi.json', 'w'))"
```

```{eval-rst}
.. openapi:: openapi.json
   :examples:
```
