import { withSentryConfig } from "@sentry/nextjs";

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
};

// Sentry build-time wrapper.
//   - Uploads source maps when SENTRY_AUTH_TOKEN is set (CI/Vercel).
//   - Hides source maps from the public bundle.
//   - Tunnels via /monitoring to bypass adblockers in the browser.
//
// To enable source-map uploads on Vercel: set SENTRY_AUTH_TOKEN
// (Sentry → Settings → Auth Tokens, scope: project:write). Optional for Phase B.
export default withSentryConfig(nextConfig, {
  org: "kai-ok",
  project: "tessera-web",
  silent: !process.env.CI,
  disableLogger: true,
  tunnelRoute: "/monitoring",
  // Skip source-map generation entirely until we set SENTRY_AUTH_TOKEN.
  // (Without the token there's no upload, and unuploaded maps just bloat the build.)
  sourcemaps: { disable: true },
});
