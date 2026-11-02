# ViPPET UI

This UI is a modern React frontend designed for building and operating visual AI workflows. The stack focuses
on fast iteration for developers and reliable, typed behavior for product features.

## Core Stack

### React + TypeScript

The app is built with React and TypeScript as the foundation. React gives us a component-first architecture
that scales well from small widgets to full feature modules, while TypeScript adds strong typing across UI
components, API contracts, and shared utilities. In practice, this reduces integration mistakes and makes
larger refactors safer.

### Routing with React Router

Navigation is handled with React Router. It provides a clear route-driven structure for pages such as
pipelines, tests, jobs, models, and media views. This keeps feature boundaries explicit and makes deep-linking
into specific screens straightforward.

### State and Data Fetching with Redux Toolkit + RTK Query

Global client state is managed with Redux Toolkit, and server communication is handled through RTK Query. This
combination gives us predictable state updates plus built-in caching, request lifecycle handling, and
generated API hooks. We also use OpenAPI-based RTK Query code generation to keep API usage consistent and
strongly typed.

### Forms with React Hook Form + Zod

For form-heavy workflows, we use React Hook Form together with Zod validation. React Hook Form keeps forms
performant with minimal re-renders, and Zod provides schema-based validation and type inference. Together,
they ensure that input data is validated early and matches expected shapes before actions are submitted.

### Pipeline Visualization with React Flow

Pipeline editing and visualization are powered by React Flow. It gives us a graph-based canvas for rendering
nodes, edges, and interactive connections in a way that feels natural for visual workflow design. This is a
core part of the product experience, enabling users to build, inspect, and reason about pipeline structure
directly in the UI.

## UI and Design System

### Tailwind CSS

Styling is based on Tailwind CSS, which helps us build consistent, token-driven UI quickly. Utility classes
keep styles close to components, while shared design tokens support consistent spacing, color usage, and
visual rhythm across the app.

### shadcn/ui-Style Component Layer

The component layer follows a shadcn/ui-style approach: composable, accessible primitives with project-level
customization. In this codebase, that is reflected in reusable UI components built with Radix-based patterns,
Tailwind utilities, and class variance helpers. The result is a clean balance between a consistent design
system and feature-level flexibility.

## Developer Experience

### Vite

Vite powers local development and production builds. It provides fast startup, responsive hot updates, and a
lightweight build pipeline, so developers can iterate on complex UI flows with minimal wait time.

### ESLint

ESLint enforces code quality and catches common issues early, including React and hook-specific pitfalls. This
keeps the codebase maintainable as the feature set grows.

### Prettier

Prettier handles code formatting automatically, reducing style-related review noise and keeping code
consistent across contributors.

## Summary

In short, the stack combines a typed React foundation, practical routing and state management, schema-driven
forms, React Flow-based pipeline visualization, and a modern Tailwind-based UI architecture. Around that core,
Vite, ESLint, and Prettier keep day-to-day development fast, consistent, and production-ready.
