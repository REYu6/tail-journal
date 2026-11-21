export async function api<T = any>(
  path: string,
  method = "GET",
  body?: unknown,
): Promise<T> {
  const multipart = body instanceof FormData;
  const result = await fetch("/api" + path, {
    method,
    credentials: "same-origin",
    cache: "no-store",
    ...(body === undefined
      ? {}
      : multipart
        ? { body }
        : {
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
          }),
  }).catch(() => {
    throw new Error("暂时连不上工作室，请检查网络后重试。");
  });
  let data;
  try {
    data = await result.json();
  } catch {
    if (result.status !== 204)
      throw new Error("工作室暂时没有响应，请稍后再试。");
  }
  if (!result.ok) {
    const hint = data?.detail ?? data?.error;
    throw new Error(
      typeof hint === "string"
        ? hint
        : result.status === 401
          ? "登录已过期，请重新登录。"
          : "提交没有成功，请核对填写的信息后重试。",
    );
  }
  return data as T;
}

export function money(cents: number) {
  return (Number(cents) / 100).toLocaleString("zh-CN", {
    maximumFractionDigits: 2,
  });
}
export interface SessionUser {
  id: string | number;
  name: string;
  email: string;
  role: string;
}
