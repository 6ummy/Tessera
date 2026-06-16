// Server-side Firebase ID-token verification — Edge-native, no firebase-admin.
//
// A Firebase ID token is a Google-signed RS256 JWT. We verify it with `jose`
// (already a dep, Web-Crypto-native like gcp-auth.ts) against Google's public
// JWKS, checking the signature + issuer + audience. This avoids pulling in
// firebase-admin (Node-only, heavy) AND avoids a service-account secret —
// verification needs only the public project id we already ship as
// NEXT_PUBLIC_FIREBASE_PROJECT_ID.
//
// What jwtVerify enforces: RS256 signature against the live JWKS, `exp`/`iat`,
// plus the issuer + audience we pass. Per Firebase's spec the issuer must be
// https://securetoken.google.com/<projectId> and the audience must be the
// project id. `sub` is the stable user uid.

import { createRemoteJWKSet, jwtVerify } from "jose";

// Google's public keys for Firebase Auth (Secure Token Service). jose caches
// and refreshes this set per its Cache-Control, so it's fetched rarely.
const JWKS = createRemoteJWKSet(
  new URL(
    "https://www.googleapis.com/service_accounts/v1/jwk/securetoken@system.gserviceaccount.com",
  ),
);

export type VerifiedUser = {
  uid: string;
  email: string | null;
  displayName: string | null;
  photoUrl: string | null;
};

/** Verify a Firebase ID token. Throws on any failure (bad signature, wrong
 *  project, expired). Returns the claims we persist. */
export async function verifyFirebaseToken(idToken: string): Promise<VerifiedUser> {
  const projectId = process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID;
  if (!projectId) {
    throw new Error("NEXT_PUBLIC_FIREBASE_PROJECT_ID is not set");
  }

  const { payload } = await jwtVerify(idToken, JWKS, {
    issuer: `https://securetoken.google.com/${projectId}`,
    audience: projectId,
  });

  // `sub` is the Firebase uid; it's always present on a valid ID token, but
  // guard anyway — an empty subject must never become a users row.
  const uid = typeof payload.sub === "string" ? payload.sub : "";
  if (!uid) throw new Error("token has no subject (uid)");

  const str = (v: unknown): string | null => (typeof v === "string" && v ? v : null);
  return {
    uid,
    email: str(payload.email),
    displayName: str(payload.name),
    photoUrl: str(payload.picture),
  };
}
