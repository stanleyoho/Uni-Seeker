# ADR-002: State Management — React Query + Context + localStorage

## Status: Accepted

## Context
Need to manage server state (API data), UI state, and persistent client state.

## Decision
- **Server state**: TanStack React Query (caching, stale-while-revalidate)
- **Auth state**: React Context
- **Theme/i18n**: React Context
- **Persistent client**: localStorage (watchlist, saved screens, theme preference)

## Rationale
- React Query eliminates manual loading/error states and provides caching
- Context is sufficient for auth/theme — no need for Redux
- localStorage is simple and works offline

## Consequences
- Multiple tabs may desync localStorage (mitigated with storage event listener)
- No global state debugger (React Query DevTools available)
