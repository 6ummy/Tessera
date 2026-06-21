// Brokerage (Alpaca) OAuth scaffolding — Phase F. Live trading is OFF-gated:
// the connect flow REFUSES unless FEATURE_LIVE_TRADING is explicitly "true"
// (it never is in the pilot). This file builds the authorize URL and reads the
// gate; it does NOT exchange tokens or place orders. The real token exchange +
// order routing land only after Phase E (legal clearance).

const ALPACA_AUTHORIZE_URL = "https://app.alpaca.markets/oauth/authorize";

/** The single gate for any brokerage-connect action. Defaults OFF; flipping it
 *  requires Phase E clearance (and even then no order path exists yet). */
export function liveTradingEnabled(): boolean {
  return process.env.FEATURE_LIVE_TRADING === "true";
}

/** Build the Alpaca OAuth authorize URL (state = the verified user id). Pure —
 *  no secret is used here (the client_id is a public OAuth app id; the secret
 *  is only needed server-side at token exchange, which this scaffolding does
 *  NOT do). Returns null when live trading is off or the app id is unset. */
export function alpacaAuthorizeUrl(userId: string): string | null {
  if (!liveTradingEnabled()) return null;
  const clientId = process.env.ALPACA_OAUTH_CLIENT_ID;
  const redirectUri = process.env.ALPACA_OAUTH_REDIRECT_URI;
  if (!clientId || !redirectUri || !userId) return null;
  const params = new URLSearchParams({
    response_type: "code",
    client_id: clientId,
    redirect_uri: redirectUri,
    scope: "account:write trading", // requested at authorize; unused pre-Phase-E
    state: userId,
  });
  return `${ALPACA_AUTHORIZE_URL}?${params.toString()}`;
}

export type BrokerStatus = {
  connected: boolean;
  provider: string | null;
  status: "disconnected" | "pending" | "connected" | "revoked";
  accountLabel: string | null;
};

export const DISCONNECTED: BrokerStatus = {
  connected: false, provider: null, status: "disconnected", accountLabel: null,
};
