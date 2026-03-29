import { createRequire } from "module";

const require = createRequire(import.meta.url);
const baseConfig = require("eslint-config-next");
const coreWebVitals = require("eslint-config-next/core-web-vitals");

const eslintConfig = [
  ...baseConfig,
  ...coreWebVitals,
  {
    rules: {
      // New rule in react-hooks plugin — flags pre-existing patterns that work correctly.
      // TODO: refactor useEffect data-fetching patterns to comply, then remove this override.
      "react-hooks/set-state-in-effect": "off",
    },
  },
];

export default eslintConfig;
