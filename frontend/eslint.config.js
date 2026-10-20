import js from '@eslint/js';
import tseslint from 'typescript-eslint';
export default tseslint.config(
  {ignores:['dist/**','test-artifacts/**']},
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {files:['src/**/*.{ts,tsx}'],languageOptions:{globals:{window:'readonly',document:'readonly',navigator:'readonly',location:'readonly',fetch:'readonly',requestAnimationFrame:'readonly',setTimeout:'readonly',clearTimeout:'readonly',console:'readonly',URL:'readonly',URLSearchParams:'readonly',AbortController:'readonly',FormData:'readonly',Blob:'readonly',HTMLElement:'readonly',HTMLInputElement:'readonly',GeoJSON:'readonly',SpeechSynthesisUtterance:'readonly'}},rules:{'no-undef':'off','@typescript-eslint/no-explicit-any':'off','@typescript-eslint/no-unused-vars':['error',{argsIgnorePattern:'^_',varsIgnorePattern:'^_'}]}}
);
