/*
 * RUNTIME configuration for the frontend.
 *
 * DEVOPS: this file exists so the SAME built frontend can run in local /
 * staging / prod. Please template or overwrite it at deploy time (entrypoint
 * script, ConfigMap, S3 object, whatever fits). Do NOT rebuild the image per
 * environment, and do NOT bake an environment's API URL into app.js.
 *
 *   apiBase: "" ............ same origin (API and web behind one proxy). Preferred
 *   apiBase: "http://localhost:8000"  ... API on a different origin (needs CORS)
 */
window.LINKR_CONFIG = {
  apiBase: "",
};
