// ESLint flat config: aturan TypeScript bertipe, React Hooks, dan Fast Refresh.
// File vendor shadcn/ui (`src/components/ui/`, dan hook `src/hooks/use-mobile.ts` yang ikut
// digenerate CLI) tidak diedit (ADR 0003). File itu tetap di-lint dan di-typecheck, tetapi tiga
// aturan yang dilanggar kode upstream dimatikan: Fast Refresh (vendor mengekspor `buttonVariants`
// bersama komponen), dan dua aturan React Compiler (`Math.random` di skeleton sidebar, `setState`
// di effect `useIsMobile`).
import js from "@eslint/js";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import { defineConfig, globalIgnores } from "eslint/config";
import globals from "globals";
import tseslint from "typescript-eslint";

export default defineConfig([
  globalIgnores(["dist", "coverage", "src/api/schema.d.ts"]),
  {
    files: ["**/*.{ts,tsx}"],
    extends: [
      js.configs.recommended,
      tseslint.configs.recommendedTypeChecked,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      globals: globals.browser,
      parserOptions: { projectService: true, tsconfigRootDir: import.meta.dirname },
    },
  },
  {
    files: ["src/components/ui/**", "src/hooks/use-mobile.ts"],
    rules: {
      "react-refresh/only-export-components": "off",
      "react-hooks/purity": "off",
      "react-hooks/set-state-in-effect": "off",
    },
  },
]);
