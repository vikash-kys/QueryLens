import js from '@eslint/js'
import globals from 'globals'
import hooks from 'eslint-plugin-react-hooks'
export default [
  { ignores: ['dist/**', 'node_modules/**'] },
  { files: ['src/**/*.{js,jsx}'], ...js.configs.recommended,
    languageOptions: { globals: globals.browser, parserOptions: { ecmaFeatures: { jsx: true } } },
    plugins: { 'react-hooks': hooks },
    rules: { 'no-unused-vars': ['error', { varsIgnorePattern: '^[A-Z_]', argsIgnorePattern: '^_' }], 'react-hooks/rules-of-hooks': 'error', 'react-hooks/exhaustive-deps': 'warn' }
  }
]
