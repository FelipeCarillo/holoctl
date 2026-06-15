// Flat ESLint config for holoctl's dashboard frontend (holoctl/server/static/js).
//
// Scope is intentionally small: a correctness net (undefined vars, unused vars,
// strict equality) for vanilla ES modules running in the browser. It is NOT a
// style formatter. Run with:  npx --yes eslint@9 holoctl/server/static/js
// (pinned to the same major the CI job uses — see .github/workflows/ci.yml).
//
// The CI `eslint` job runs this as a BLOCKING check: the cross-module-global
// references that used to trip `no-undef` were fixed by the shared-module
// refactor (api.js / dom.js / util.js / popover.js) in the same branch.
export default [
  {
    // Third-party minified bundles (mermaid.min.js) are not ours to lint.
    ignores: ["holoctl/server/static/js/vendor/**"],
  },
  {
    files: ["holoctl/server/static/js/**/*.js"],
    languageOptions: {
      ecmaVersion: "latest",
      sourceType: "module",
      globals: {
        // Browser environment globals the dashboard relies on.
        window: "readonly",
        document: "readonly",
        localStorage: "readonly",
        sessionStorage: "readonly",
        fetch: "readonly",
        EventSource: "readonly",
        setTimeout: "readonly",
        clearTimeout: "readonly",
        setInterval: "readonly",
        clearInterval: "readonly",
        requestAnimationFrame: "readonly",
        cancelAnimationFrame: "readonly",
        console: "readonly",
        navigator: "readonly",
        location: "readonly",
        history: "readonly",
        URL: "readonly",
        URLSearchParams: "readonly",
        FormData: "readonly",
        CustomEvent: "readonly",
        Event: "readonly",
        MutationObserver: "readonly",
        IntersectionObserver: "readonly",
        getComputedStyle: "readonly",
        alert: "readonly",
        confirm: "readonly",
        prompt: "readonly",
      },
    },
    rules: {
      "no-undef": "error",
      "no-unused-vars": "warn",
      eqeqeq: "error",
    },
  },
];
