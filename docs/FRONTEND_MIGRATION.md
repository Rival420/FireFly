# Frontend Migration Plan (CRA → Vite)

## Rationale
Create React App (CRA) shows deprecation warnings and is no longer maintained. Migrating to Vite improves build speed, dev experience, and long-term support while keeping React 18 and MUI 5.

## Target Stack
- Build: Vite + React (SWC)
- Language: TypeScript (already adopted)
- UI: MUI v5 (unchanged)
- State/Data: React Query (unchanged)

## Steps
1. Add Vite config with React plugin and TypeScript support.
2. Replace CRA scripts in `package.json` with Vite scripts (`dev`, `build`, `preview`).
3. Update HTML entry (Vite `index.html` at project root). Remove CRA-specific files.
4. Adjust environment variables (`VITE_` prefix). Use `VITE_API_URL` instead of `REACT_APP_API_URL`.
5. Update Dockerfile to use `npm run build` and serve static build (either:
   - Vite preview for dev, or
   - Nginx for prod with a minimal config).
6. Verify HMR / build; update README and CI.

## Dev/Prod Profiles
- Dev: `vite dev` on port 3000 (same mapping).
- Prod: `vite build` + Nginx serving `dist/` (or backend serves static under a prod profile).

## Rollout
- Work on a migration branch; keep CRA until Vite is validated.
- Update `.cursorrules` and docs post-merge.

## Security
- No change in network egress; Axios and API contracts remain.
- Backend SSRF/CORS controls unchanged.


