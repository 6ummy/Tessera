// Next.js instrumentation hook — runs once when the server starts.
// Loads the matching Sentry config for the active runtime.

export async function register() {
  if (process.env.NEXT_RUNTIME === "nodejs") {
    await import("./sentry.server.config");
  }
  if (process.env.NEXT_RUNTIME === "edge") {
    await import("./sentry.edge.config");
  }
}

// Forward route-handler errors to Sentry (Next.js 15 will require this).
export { captureRequestError as onRequestError } from "@sentry/nextjs";
