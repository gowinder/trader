import { createCookieSessionStorage, redirect } from "react-router";
import bcrypt from "bcryptjs";
import { db } from "../../db";
import { systemSettings } from "../../db/schema";
import { eq } from "drizzle-orm";

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

const SALT_ROUNDS = 12;
const PASSWORD_KEY = "dashboard_password";

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

export async function initializePassword() {
  const existing = await db
    .select()
    .from(systemSettings)
    .where(eq(systemSettings.key, PASSWORD_KEY));

  if (existing.length > 0) return;

  const envPassword = process.env.DASHBOARD_PASSWORD;
  if (!envPassword) {
    throw new Error("DASHBOARD_PASSWORD must be set for initial setup");
  }

  const hashed = await bcrypt.hash(envPassword, SALT_ROUNDS);
  await db.insert(systemSettings).values({
    key: PASSWORD_KEY,
    value: hashed,
  });
}

export async function verifyPassword(password: string): Promise<boolean> {
  const result = await db
    .select()
    .from(systemSettings)
    .where(eq(systemSettings.key, PASSWORD_KEY));

  if (result.length === 0) {
    throw new Error("Password not initialized");
  }

  return bcrypt.compare(password, result[0].value);
}

export async function changePassword(
  oldPassword: string,
  newPassword: string
): Promise<{ success: boolean; error?: string }> {
  const valid = await verifyPassword(oldPassword);
  if (!valid) {
    return { success: false, error: "旧密码错误" };
  }

  const hashed = await bcrypt.hash(newPassword, SALT_ROUNDS);
  await db
    .update(systemSettings)
    .set({ value: hashed, updatedAt: new Date() })
    .where(eq(systemSettings.key, PASSWORD_KEY));

  return { success: true };
}

// 自动初始化密码（模块加载时执行一次）
initializePassword().catch((err) => {
  console.error("Failed to initialize password:", err.message);
});
