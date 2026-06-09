// Flat ESLint config for holoctl's dashboard frontend (holoctl/server/static/js).
//
// Scope is intentionally small: a correctness net (undefined vars, unused vars,
// strict equality) for vanilla ES modules running in the browser. It is NOT a
// style formatter. Run with:  npx --yes eslint holoctl/server/static/js
//
// NOTE: the JS modules currently reference each other's functions as globals,
// which trips `no-undef`. That is fixed on a separate frontend branch, so the
// CI job that runs this is `continue-on-error: true` (non-blocking) until that
// branch merges — see .github/workflows/ci.yml.
export default [
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
