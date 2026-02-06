import { createCookieSessionStorage, redirect } from "react-router";

const sessionSecret = process.env.SESSION_SECRET;
if (!sessionSecret) {
  throw new Error("SESSION_SECRET must be set");
}

const storage = createCookieSessionStorage({
  cookie: {
    name: "_session",
    httpOnly: true,
    maxAge: 60 * 60 * 24 * 7, // 7 days
    path: "/",
    sameSite: "lax",
    secrets: [sessionSecret],
    // 只有在显式启用 HTTPS 时才设置 secure
    secure: process.env.COOKIE_SECURE === "true",
  },
});

export async function getSession(request: Request) {
  return storage.getSession(request.headers.get("Cookie"));
}

export async function createUserSession(redirectTo: string) {
  const session = await storage.getSession();
  session.set("authenticated", true);
  session.set("authenticatedAt", Date.now());
  return redirect(redirectTo, {
    headers: {
      "Set-Cookie": await storage.commitSession(session),
    },
  });
}

export async function logout(request: Request) {
  const session = await getSession(request);
  return redirect("/login", {
    headers: {
      "Set-Cookie": await storage.destroySession(session),
    },
  });
}

export async function requireAuth(request: Request) {
  const session = await getSession(request);
  const authenticated = session.get("authenticated");

  if (!authenticated) {
    throw redirect("/login");
  }

  return session;
}

export async function isAuthenticated(request: Request) {
  const session = await getSession(request);
  return session.get("authenticated") === true;
}

export function verifyPassword(password: string) {
  const dashboardPassword = process.env.DASHBOARD_PASSWORD;
  if (!dashboardPassword) {
    throw new Error("DASHBOARD_PASSWORD must be set");
  }
  return password === dashboardPassword;
}
