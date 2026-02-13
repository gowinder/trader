import type { ActionFunctionArgs } from "react-router";
import { requireAuth, changePassword } from "~/services/auth.server";

export async function action({ request }: ActionFunctionArgs) {
  await requireAuth(request);

  if (request.method !== "POST") {
    return Response.json({ success: false, error: "Method not allowed" }, { status: 405 });
  }

  const body = await request.json();
  const { oldPassword, newPassword } = body;

  if (!oldPassword || !newPassword) {
    return Response.json({ success: false, error: "请填写所有字段" }, { status: 400 });
  }

  if (newPassword.length < 6) {
    return Response.json({ success: false, error: "新密码至少 6 位" }, { status: 400 });
  }

  const result = await changePassword(oldPassword, newPassword);
  if (!result.success) {
    return Response.json({ success: false, error: result.error }, { status: 400 });
  }

  return Response.json({ success: true });
}
