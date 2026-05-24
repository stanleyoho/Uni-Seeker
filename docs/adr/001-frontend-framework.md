# ADR-001: Frontend Framework — Next.js + React

## Status: Accepted

## Context
Need a modern frontend framework for a stock analysis platform with SSR, file-based routing, and good TypeScript support.

## Decision
Use Next.js 16 (App Router) with React 19.

## Rationale
- App Router provides clean page organization for 15+ routes
- React Query (TanStack) handles server state caching efficiently
- TypeScript ensures type safety across API boundaries
- Next.js image optimization and code splitting for performance

## Alternatives Considered
- **Vite + React**: Faster dev build but no SSR, no file-based routing
- **Remix**: Good alternative but smaller ecosystem
- **Vue/Nuxt**: Team expertise is in React

## Consequences
- Must handle "use client" directives for client components
- Bundle size larger than Vite due to Next.js runtime
