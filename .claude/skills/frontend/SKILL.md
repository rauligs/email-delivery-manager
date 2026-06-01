---
name: react-next-frontend-engineering
version: 1.2.1
description: Use this skill for React and Next.js web frontend work covering architecture, TypeScript, Tailwind CSS, accessibility, testing, performance, security/privacy, SEO/AI search, i18n, observability, and release readiness. Do not use for React Native, Vue, Svelte, Angular, CLI tools, backend-only work, or non-web UI.
tags:
  - react
  - nextjs
  - frontend
  - tailwindcss
  - accessibility
  - performance
  - security
  - seo
---

# Frontend Engineering Standards

This skill applies only to React and Next.js web projects. Do not use it for React Native, Vue, Svelte, Angular, CLI tools, backend-only work, or non-web UI.

Use this skill to deliver production-quality frontend work. Prefer the project's existing framework, versions, package manager, design system, test setup, and deployment model. Do not upgrade frameworks or introduce new libraries unless the task requires it or the tradeoff is explicit.

For version-sensitive behavior, verify against official documentation when adopting a feature not already used in the codebase. Treat beta, canary, experimental, and proposal-stage features as opt-in, not defaults.

## Agent Workflow

When invoked:

1. Choose scope using the Scope Guide, then run the matching discovery depth. For non-tiny changes, run the discovery pass in §1 before choosing an implementation approach.
2. Identify the change type: new UI, refactor, bug fix, performance, accessibility, SEO/content, security, test, or release work.
3. Apply only the sections relevant to that change type; do not expand scope because a standard mentions a related concern.
4. Prefer existing project conventions over this skill when they conflict, unless the local pattern is clearly broken for the requested task.
5. Implement the change, then run the smallest verification set that proves it using §9, §15, and project scripts.
6. Before reporting done, self-run §16 Closing Checklist and call out any item that could not be verified.

## Scope Guide

- For tiny changes under roughly 20 lines, use the quick path: inspect the touched files, apply only the directly relevant section, check §7 if visible UI changed, then run §16. Do not add tests, telemetry, SEO metadata, state handling, or new abstractions unless the touched behavior requires them.
- For single-component UI changes, apply relevant design, Tailwind, accessibility, and local test guidance only. Do not create app-wide patterns.
- For public, indexable, content-bearing pages, include §11. For internal dashboards, authenticated tools, and non-indexable routes, skip SEO and AI-discovery work unless requested.
- For high-risk flows such as auth, checkout, payments, data loss, permissions, uploads, and editor workflows, broaden verification to include relevant negative paths.
- Apply §9 tests and §14 instrumentation only to behavior the change actually affects. Enumerated states and signals are prompts to choose from, not a requirement to implement all of them.

## 1. Discovery Workflow

- Scale discovery to task size. Tiny changes usually need only the touched files and local imports; architecture changes need `package.json`, lockfiles, framework config, routing structure, CSS entry points, test config, CI files, and deployment settings.
- Identify whether the app is content, commerce, SaaS, dashboard, marketing, docs, game, or internal tooling; optimize UX density, copy, layout, and testing strategy for that product type.
- Map critical flows: first visit, auth, navigation, forms, checkout/payment, search/filtering, content publishing, account settings, and error recovery.
- Check browser support, localization requirements, accessibility obligations, SEO goals, analytics needs, and security/privacy constraints.
- Keep changes scoped. Reuse local components, tokens, hooks, data clients, schema validators, and error boundaries where they already exist.

## 2. Architecture

- Use semantic HTML and progressive enhancement first; JavaScript should enrich a usable document, not hide all core content from crawlers and assistive tech.
- Prefer server rendering, static generation, streaming, and edge/CDN caching for public or content-heavy pages. Use client rendering for truly interactive surfaces.
- In React and Next.js, default to Server Components where available and keep `"use client"` boundaries leaf-level.
- Separate data loading, validation, authorization, mutation, presentation, and analytics concerns. Do not bury security-sensitive checks inside UI-only guards.
- Use schema validation at trust boundaries with tools already present in the project, such as Zod, Valibot, Yup, TypeBox, or framework-native validators.
- Model loading, empty, error, offline, unauthorized, and partial-data states the user can actually reach in this app. Do not add states for impossible cases.
- Choose state location deliberately: local state for isolated UI, URL state for shareable filters and pagination, framework loaders/RSC for server-owned data, TanStack Query/SWR or existing equivalents for client server-state caching, and Zustand/Jotai/Redux-style stores only for cross-cutting client state.
- For complex UI primitives, prefer proven accessible libraries already in the stack over hand-rolled widgets.

<!-- VERSION-SENSITIVE: re-verify quarterly -->
## 3. React And Next.js

- Keep components small enough to test and reason about, but avoid abstractions that only rename JSX.
- If a component uses state, effects, refs, browser APIs, or event handlers, it must be a Client Component. There is no judgment call; move only the server-safe parent or data-fetching portion to a Server Component.
- In React 19 projects, use `ref` as a prop for new function components when consistent with existing project patterns.
- For new or materially changed mutation flows, prefer current React 19 primitives when consistent with existing project patterns: Actions with `useActionState`, `useOptimistic`, and `useFormStatus` for mutation state, and `use` only where the installed framework supports the data source.
- Use Suspense intentionally for streaming and partial loading. Provide stable fallbacks that do not cause layout shifts.
- Pair Suspense with error boundaries, reset paths, retry affordances, and telemetry so streamed or deferred sections fail independently instead of blanking the whole route.
- In Next.js App Router, use metadata APIs, route handlers, Server Actions, `sitemap`, `robots`, and structured layouts according to the app's version.
- Check the installed Next.js version for the current request-interception convention, such as `middleware.ts` or `proxy.ts`. Use it for headers, redirects, rewrites, and lightweight request decisions, not slow data fetching or full authorization.
- Use Cache Components, `use cache`, Partial Prerendering, or similar framework features only when supported by the installed version and production requirements.
- For Edge runtime targets, verify Node API availability, database driver compatibility, crypto support, request body limits, region placement, cold-start behavior, and logging/observability before moving logic out of the Node runtime.
- Optimize images with framework-native image components when available. Always provide dimensions or responsive `sizes`, meaningful `alt`, and priority/preload only for true LCP candidates.
- Use dynamic imports for large non-critical UI, heavy editors, charts, maps, video players, and admin-only features.

<!-- VERSION-SENSITIVE: re-verify quarterly -->
## 4. TypeScript

- Keep `strict` enabled unless the project has a documented migration reason with an in-repo comment, issue, ADR, or config note. Add precise types at public boundaries, not noisy annotations everywhere.
- Run `tsc --noEmit` or the framework-equivalent typecheck in CI.
- Prefer discriminated unions for UI states and API results. Avoid `any`; use `unknown` plus narrowing at untrusted boundaries.
- Use `moduleResolution: "bundler"` or `nodenext` based on the framework/runtime, not by habit.
- For TypeScript upgrades, read release notes, address deprecated compiler options before adopting the next major version, and do not rely on beta compiler behavior unless requested.

<!-- VERSION-SENSITIVE: re-verify quarterly -->
## 5. Tailwind CSS

- In Tailwind v4 projects, use `@import "tailwindcss"` and define design tokens with `@theme` in CSS.
- Keep JavaScript config only when the project explicitly needs backward-compatible configuration.
- Use theme variables as the source of truth for colors, spacing, typography, radii, shadows, breakpoints, and motion.
- Avoid one-off arbitrary values in view code unless the value comes from an external asset, third-party embed, measured layout constraint, or other non-tokenizable requirement. Arbitrary values are acceptable in design-system or shared component files when they encode an intentional primitive.
- Use `@source` for files or packages that automatic content detection cannot see.
- Safelist with CSS-first mechanisms such as `@source inline()` when needed.
- Prefer canonical v4 utilities in v4 projects, including modern gradient, grow, shrink, container-query, data-attribute, and state variants.
- Prefer modern CSS primitives before JavaScript layout workarounds: container queries for component responsiveness, subgrid for nested alignment, cascade layers for override order, custom properties and `@property` for tokens and animation, logical properties for RTL, `:has()` for parent/state selectors, and OKLCH or `color-mix()` when browser targets support them.
- Keep utility composition readable. Extract components for repeated UI behavior; use CSS modules, `@layer`, or local CSS for complex selectors, animations, and third-party overrides.
- Verify dark mode, forced colors, reduced motion, RTL, print, container sizes, and high-contrast states when relevant.
- Do not let Tailwind class strings become a substitute for design decisions. Components should still express clear layout, density, hierarchy, and interaction states.

Example:

```html
<!-- Avoid: repeated magic spacing that should be a token -->
<section class="mt-[37px] px-[19px]">...</section>

<!-- Prefer: theme-backed spacing -->
<section class="mt-10 px-5">...</section>

<!-- Acceptable exception: fixed third-party ad slot -->
<aside class="h-[250px] w-[300px]" data-ad-slot></aside>
```

## 6. Design Systems And UX

- Use existing tokens, primitives, icon libraries, spacing rhythm, border radius, and density. Do not create a parallel design language.
- Match UI composition to the product: operational tools should be dense, calm, and scannable; editorial or marketing pages may be more expressive.
- For controls you create or materially change, build the relevant states: hover, focus-visible, active, disabled, loading, selected, expanded, invalid, empty, destructive, and success. Do not add unused states to untouched components.
- Reserve cards for repeated items, modals, and genuinely framed tools. Avoid cards inside cards and decorative backgrounds that reduce clarity.
- Use stable dimensions for boards, grids, toolbars, icon buttons, counters, and tiles so dynamic text or icons do not shift layout.
- Avoid raw `vw`-based font sizing. If fluid typography is needed for marketing or editorial layouts, use `clamp()` with sensible minimum and maximum sizes.
- Ensure text never overlaps or escapes its container. Long labels, localized strings, and dynamic data must wrap, truncate intentionally, or resize within clear constraints.
- Use icons for familiar tools, tooltips for ambiguous icon-only controls, and text labels for commands whose meaning is not obvious.

## 7. Accessibility

- Target WCAG 2.2 AA unless the project has a stricter requirement.
- Use native HTML controls before ARIA. Add ARIA only when native semantics cannot express the widget, then implement keyboard behavior and state updates completely.
- Every interactive element must be keyboard reachable, visibly focusable, correctly named, and operable without pointer-only gestures.
- Associate labels, descriptions, validation errors, and help text with form fields. Preserve user input on validation failure.
- Maintain logical heading order, landmarks, skip links for large apps, meaningful link text, and accurate document language.
- Provide useful `alt` text for informative images and empty `alt` for decorative images.
- Respect `prefers-reduced-motion`, color contrast, zoom to 200% or more, target size, focus not obscured, and non-color indicators.
- Use existing automated accessibility checks when they already cover the touched surface; otherwise do targeted keyboard and semantics review unless the changed surface warrants automation. For high-risk UI, such as auth, checkout, payments, destructive actions, modal focus traps, rich text editors, and custom comboboxes, also test with at least one screen reader/browser combination when available; otherwise report it as not verified.
- Do not add accessibility test infrastructure for trivial changes; use existing checks and targeted manual keyboard/semantics review unless the changed surface warrants automation.

Example:

```html
<!-- Avoid: incomplete button semantics and keyboard behavior -->
<div role="button" onclick="save()">Save</div>

<!-- Prefer: native control -->
<button type="button">Save</button>
```

## 8. Performance

- Optimize for user-perceived speed and Core Web Vitals: LCP <= 2.5s, INP <= 200ms, CLS <= 0.1 at the 75th percentile, segmented by mobile and desktop. Treat INP <= 200ms as the good threshold; high-interaction products should aim lower where practical.
- Measure before and after with the project's tools, such as Lighthouse, WebPageTest, Chrome DevTools, Playwright traces, bundle analyzers, RUM, or platform analytics.
- Reduce JavaScript by moving work server-side, deleting unused dependencies, code-splitting heavy routes, and avoiding hydration for static content.
- Protect LCP: serve the right image size and format, preload only the likely LCP asset, avoid late font swaps, and keep critical CSS small.
- Protect INP: avoid long tasks over 50ms, debounce or defer expensive work, virtualize large lists, memoize only where profiling shows value, and move heavy computation to workers when appropriate.
- Protect CLS: reserve dimensions for images, ads, embeds, skeletons, and dynamic panels. Avoid injecting banners above existing content without reserved space.
- Cache deliberately with HTTP headers, CDN rules, revalidation, route-level caching, and framework data caches. Document invalidation behavior for dynamic content.
- Load third-party scripts through an allowlist and budget. Defer, lazy-load, sandbox, or remove tags that do not justify their cost.

## 9. Testing

- Build the smallest test mix that protects the change: static checks, unit tests, component tests, accessibility checks, integration tests, and E2E tests where each adds distinct confidence.
- Use Vitest or the project's unit runner for utilities, hooks, reducers, schema validation, formatters, and synchronous components.
- Use Testing Library or framework-native test utilities to assert behavior through roles, labels, text, and user-visible state instead of implementation details.
- For browser-specific component behavior, use real-browser testing where available, such as Vitest Browser Mode, Playwright component tests, or the existing setup.
- Use Playwright for critical E2E flows, routing, auth, cookies, redirects, proxy behavior, file uploads, payments, visual regressions, and cross-browser coverage.
- Reuse authenticated storage state, seed deterministic data, mock network calls at stable boundaries, and avoid sleeps. Prefer auto-waiting assertions.
- Include negative paths: validation errors, expired sessions, permission failures, empty data, slow network, offline or retry flows, and server errors.
- Add accessibility checks with axe or equivalent, but do not treat automated a11y tests as complete coverage.
- Add visual regression tests only for stable, high-value surfaces. Mask dynamic regions and keep snapshots reviewable.
- CI should run lint, typecheck, unit tests, relevant E2E tests, build, and any required bundle/performance budgets.
- Do not scaffold new test infrastructure for trivial changes. Use existing tests and commands first; add a new layer only when it protects changed behavior that existing coverage cannot observe.

## 10. Security And Privacy

- Apply server-boundary controls when the task touches auth, headers, routing, forms or Server Actions, uploads, rich text, redirects, third-party scripts, or server-rendered user data. For pure presentational changes, limit security review to client-visible risks in the touched files.
- Treat all user input, URL params, search params, cookies, headers, CMS content, markdown, and third-party data as untrusted.
- Rely on framework escaping by default. Avoid `dangerouslySetInnerHTML`; if unavoidable, sanitize with a maintained allowlist sanitizer and test dangerous inputs.
- Enforce authorization inside server-side loaders, route handlers, API routes, and Server Actions. Client checks are UX only.
- Choose an explicit browser session strategy. Prefer secure `HttpOnly` cookie sessions for browser apps; if bearer tokens are required, avoid long-lived tokens in `localStorage` and plan refresh, rotation, revocation, and XSS exposure.
- Use CSRF protection for cookie-authenticated mutations, including forms and Server Actions. SameSite cookies help but do not replace proper CSRF defenses where required.
- Validate `Origin` and `Referer` for sensitive same-site mutations when the framework or platform does not already enforce an equivalent protection.
- Set session cookies with `HttpOnly`, `Secure`, explicit `SameSite`, narrow `Path`, and `__Host-` prefixes when possible.
- Use CSP to restrict scripts, styles, images, frames, connections, and workers. Prefer hashes or nonces for strict policies; understand that per-request nonces can force dynamic rendering in some frameworks.
- Use SRI for third-party scripts and styles when resources are static and cross-origin requirements are satisfied.
- Avoid leaking secrets into client bundles, logs, error messages, source maps, analytics events, or public environment variables.
- Validate redirect destinations, file uploads, rich text, SVGs, postMessage origins, iframe permissions, and URL construction.
- Minimize personal data collection. Gate analytics and marketing pixels according to consent requirements, regional law, and project policy.
- Keep dependency risk visible with lockfiles, package audits, Dependabot or equivalent, and minimal third-party script vendors.

Examples:

```ts
// Avoid: attacker-controlled navigation.
window.location.href = new URLSearchParams(location.search).get("next") || "/";

// Prefer: allow only internal destinations.
const next = new URLSearchParams(location.search).get("next");
window.location.href = next && next.startsWith("/") && !next.startsWith("//") ? next : "/";
```

```tsx
// Avoid: rendering CMS HTML without sanitization.
<article dangerouslySetInnerHTML={{ __html: cmsHtml }} />

// Prefer: sanitize at the HTML boundary with the project's approved sanitizer.
<article dangerouslySetInnerHTML={{ __html: sanitizeCmsHtml(cmsHtml) }} />
```

<!-- VERSION-SENSITIVE: re-verify quarterly -->
## 11. SEO And AI Discoverability

- Apply this section only to public, indexable, content-bearing pages or when SEO/AI discovery is explicitly requested.
- Start with fundamentals: crawlable URLs, fast pages, textual primary content, valid HTML, internal links, canonical URLs, robots rules, sitemaps, redirects, metadata, and stable status codes.
- Use framework metadata APIs for title, description, canonical, alternates, Open Graph, Twitter/X cards, icons, theme color, and robots directives.
- Generate `sitemap.xml` and `robots.txt` from source-of-truth routes when possible. Do not block CSS, JS, or content needed for rendering unless intentionally private.
- Use JSON-LD structured data that matches visible page content. Choose schema types that Google and target platforms actually support, such as Organization, Product, Article, BreadcrumbList, FAQPage, Event, LocalBusiness, Review, or SoftwareApplication when applicable.
- Include hreflang and localized canonical strategy for international sites. Keep language, region, currency, and availability consistent.
- Optimize images and video for discovery with descriptive filenames, alt text, captions/transcripts when useful, dimensions, and structured data when relevant.
- For JavaScript-heavy pages, ensure important content and links are present in server-rendered HTML or otherwise reliably renderable by crawlers.
- For AI Overviews and AI Mode in Google Search, no special AI markup is required; the same SEO fundamentals, useful content, page experience, crawlability, textual content, and matching structured data remain the baseline.
- For AI search visibility, make public content answer the page's primary query in plain text, expose authorship or provenance when relevant, keep facts and dates current, link canonical source material, and remove keyword-stuffed or model-targeted filler.
- Use `llms.txt` only as an optional emerging convention, especially for docs, APIs, SaaS, and knowledge-heavy sites. Keep it concise, markdown-formatted, rooted at `/llms.txt`, and linked to canonical docs or markdown resources. Do not claim it is required for Google AI features.
- Use snippet controls intentionally: `nosnippet`, `data-nosnippet`, `max-snippet`, `noindex`, and crawler-specific controls affect what search systems may show or index.
- Validate with Search Console, Rich Results Test, URL Inspection, social preview debuggers, sitemap checks, and log analysis.

## 12. Internationalization

- Externalize user-facing strings unless the project is explicitly single-locale.
- Design for text expansion, RTL, plural rules, locale-specific sorting, date/time, numbers, currencies, names, addresses, and units.
- Use semantic `lang`, `dir`, localized metadata, localized routes, translated alt text, and hreflang where public pages have language variants.
- Avoid concatenating translated strings from fragments that break grammar in other languages.

## 13. Forms And Data Entry

- Use native form semantics where possible. Make submission work with Enter and assistive technology.
- Validate on the client for feedback and on the server for enforcement. Client validation is never a reason to skip server validation. Share schemas only when it does not leak server-only rules.
- For React or Next.js Server Actions and Server Functions, treat form submissions as server-side mutations: validate `FormData`, authenticate and authorize, enforce CSRF/origin protections, return serializable state, and handle revalidation or cache invalidation explicitly.
- Use `useActionState`, `useFormStatus`, `useOptimistic`, or framework equivalents for pending, error, success, and optimistic UI without breaking progressive enhancement.
- Show field-level errors, preserve entered values, focus the first meaningful error, and summarize errors for long forms.
- Support autofill, password managers, input modes, autocomplete attributes, paste, undo, and accessible authentication.
- Prevent duplicate submissions with idempotency, disabled/loading states, optimistic UI rollback, and clear recovery paths.

Example:

```ts
// Avoid: trusting client-side validation.
export async function updateEmail(formData: FormData) {
  await saveEmail(String(formData.get("email")));
}

// Prefer: validate and authorize in the server mutation.
export async function updateEmail(formData: FormData) {
  const user = await requireUser();
  const email = emailSchema.parse(formData.get("email"));
  await saveEmailForUser(user.id, email);
}
```

## 14. Observability And Analytics

- When the changed behavior affects observability, instrument important frontend errors, route transitions, Web Vitals, failed requests, form failures, search zero-results, and conversion events.
- Use source maps securely. Do not expose private source maps publicly unless the deployment policy allows it.
- Keep analytics schemas documented and typed when possible. Avoid sending PII, secrets, tokens, or raw free-text input.
- Add feature flags, experiment assignment, and logging only for changed behavior that needs them, in a way that is testable and does not break caching assumptions.
- Treat feature flags as read-only configuration at app or route boundaries; do not turn them into mutable app state unless the product explicitly requires runtime editing.

## 15. Build, Release, And Maintenance

- Use existing package scripts such as `dev`, `build`, `start`, `lint`, `typecheck`, `test`, `test:e2e`, and `format` or project equivalents. Normalize scripts only when the task is build or release tooling.
- Run production builds before final handoff when build behavior matters. Development success is not enough.
- Keep bundle budgets, browserslist or target browsers, transpilation policy, and polyfill strategy aligned with product requirements.
- Preserve lockfiles. Do not churn formatter output, generated files, or dependency versions outside the task scope.
- Document required environment variables without exposing values. Fail fast on missing runtime configuration.
- Confirm deployment headers, caching, redirects, compression, image optimization, and source map policy in the target platform.

## 16. Closing Checklist

Before reporting done, self-check:

- The changed surfaces work across applicable target viewport sizes, input methods, themes, and core browsers.
- Content is accessible, crawlable where public, localized where required, and resilient to long or missing data.
- Security-sensitive behavior is enforced on the server and covered by tests or review notes.
- Performance impact is measured or bounded, with no unexplained bundle or Web Vitals regression.
- Tests, typecheck, lint, build, and relevant E2E checks pass, or any skipped verification is explicitly reported with the reason.
