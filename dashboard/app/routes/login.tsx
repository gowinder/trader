import { useState } from "react";
import { Form, useActionData, useNavigation } from "react-router";
import type { Route } from "./+types/login";
import { Button } from "~/components/ui/button";
import { Input } from "~/components/ui/input";
import { Label } from "~/components/ui/label";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "~/components/ui/card";
import { createUserSession, isAuthenticated, verifyPassword } from "~/services/auth.server";
import { redirect } from "react-router";

export async function loader({ request }: Route.LoaderArgs) {
  const authenticated = await isAuthenticated(request);
  if (authenticated) {
    return redirect("/dashboard");
  }
  return null;
}

export async function action({ request }: Route.ActionArgs) {
  const formData = await request.formData();
  const password = formData.get("password");

  if (typeof password !== "string" || password.length === 0) {
    return { error: "请输入密码" };
  }

  if (!verifyPassword(password)) {
    return { error: "密码错误" };
  }

  return createUserSession("/dashboard");
}

export default function LoginPage() {
  const actionData = useActionData<typeof action>();
  const navigation = useNavigation();
  const isSubmitting = navigation.state === "submitting";
  const [showPassword, setShowPassword] = useState(false);

  return (
    <div className="flex min-h-screen items-center justify-center bg-background p-4">
      <Card className="w-full max-w-sm">
        <CardHeader className="text-center">
          <CardTitle className="text-2xl">Trader Dashboard</CardTitle>
          <CardDescription>请输入密码登录</CardDescription>
        </CardHeader>
        <CardContent>
          <Form method="post" className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="password">密码</Label>
              <div className="relative">
                <Input
                  id="password"
                  name="password"
                  type={showPassword ? "text" : "password"}
                  autoComplete="current-password"
                  required
                  autoFocus
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                >
                  {showPassword ? "隐藏" : "显示"}
                </button>
              </div>
            </div>

            {actionData?.error && (
              <p className="text-sm text-destructive">{actionData.error}</p>
            )}

            <Button type="submit" className="w-full" disabled={isSubmitting}>
              {isSubmitting ? "登录中..." : "登 录"}
            </Button>
          </Form>
        </CardContent>
      </Card>
    </div>
  );
}
