import { User, UserManager, WebStorageStateStore } from "oidc-client-ts";

const authority = import.meta.env.VITE_CASDOOR_AUTHORITY ?? "http://localhost:8000";
const clientId = import.meta.env.VITE_CASDOOR_CLIENT_ID ?? "osb-console";
const redirectUri = import.meta.env.VITE_CASDOOR_REDIRECT_URI ?? `${window.location.origin}/`;
const postLogoutRedirectUri =
  import.meta.env.VITE_CASDOOR_POST_LOGOUT_REDIRECT_URI ?? `${window.location.origin}/`;
const scope = import.meta.env.VITE_CASDOOR_SCOPE ?? "openid profile email";

let userManager: UserManager | null = null;

export type OidcSession = {
  accessToken: string;
  profile: {
    sub?: string;
    name?: string;
    preferred_username?: string;
    email?: string;
  };
  expiresAt?: number;
};

export function getOidcConfig() {
  return {
    authority,
    clientId,
    redirectUri,
    postLogoutRedirectUri,
    scope
  };
}

export function getUserManager() {
  if (userManager) return userManager;
  userManager = new UserManager({
    authority,
    client_id: clientId,
    redirect_uri: redirectUri,
    post_logout_redirect_uri: postLogoutRedirectUri,
    response_type: "code",
    scope,
    automaticSilentRenew: false,
    loadUserInfo: true,
    userStore: new WebStorageStateStore({ store: window.localStorage })
  });
  return userManager;
}

export async function getOidcSession(): Promise<OidcSession | null> {
  const user = await getUserManager().getUser();
  return user && !user.expired ? sessionFromUser(user) : null;
}

export async function completeSigninRedirect(): Promise<OidcSession | null> {
  const user = await getUserManager().signinRedirectCallback();
  window.history.replaceState({}, document.title, window.location.pathname || "/");
  return sessionFromUser(user);
}

export async function signinRedirect() {
  await getUserManager().signinRedirect();
}

export async function signoutRedirect() {
  await getUserManager().signoutRedirect();
}

export async function removeOidcSession() {
  await getUserManager().removeUser();
}

export function hasSigninResponse(url = window.location.href) {
  const parsed = new URL(url);
  return parsed.searchParams.has("code") && parsed.searchParams.has("state");
}

function sessionFromUser(user: User): OidcSession {
  return {
    accessToken: user.access_token,
    profile: user.profile,
    expiresAt: user.expires_at
  };
}
