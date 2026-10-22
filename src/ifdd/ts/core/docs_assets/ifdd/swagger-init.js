/*
 * Starts Swagger UI on /docs of the IFDD time series API.
 *
 * Part of ifdd-ts-core (BSD-3-Clause). The page that loads this file has no
 * inline script, so it works under a Content-Security-Policy with
 * script-src 'self'. The URL of the OpenAPI document is read from the
 * attribute data-openapi-url of the element #swagger-ui.
 *
 * There is no OAuth2 login: the API takes tokens of the client credentials
 * grant, which are pasted under "Authorize" (bearer token).
 *
 *   persistAuthorization  keeps the pasted token across page reloads (in the
 *                         browser's localStorage of this host)
 *   validatorUrl: null    no request to the public swagger.io validator
 */
(function () {
  "use strict";

  var element = document.getElementById("swagger-ui");

  window.ui = SwaggerUIBundle({
    url: element.dataset.openapiUrl,
    dom_id: "#swagger-ui",
    layout: "BaseLayout",
    deepLinking: true,
    showExtensions: true,
    showCommonExtensions: true,
    persistAuthorization: true,
    validatorUrl: null,
    presets: [
      SwaggerUIBundle.presets.apis,
      SwaggerUIBundle.SwaggerUIStandalonePreset
    ]
  });
})();
