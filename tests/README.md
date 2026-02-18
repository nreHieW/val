# Tests

This folder contains parity tests to ensure the TypeScript DCF model matches the original Python implementation.

- `fixtures/`: precomputed Python outputs used as golden test data
- `_python/`: original Python model + fixture generator
- `dcf.test.ts`: Bun tests that compare TS outputs against fixtures

## Commands

- Regenerate fixtures (runs Python once):
  - `bun run test:fixtures:python`
- Run tests (no Python required):
  - `bun test`
