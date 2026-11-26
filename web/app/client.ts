export type Research = { id: string; question: string; is_demo?: boolean };

export async function api<T>(route: string, options?: RequestInit): Promise<T> {
  const response = await fetch("/api/research" + route, { cache: "no-store", ...options });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(typeof data.detail === "string" ? data.detail : "Не удалось выполнить запрос. Проверьте введённые данные.");
  }
  return response.json();
}

export function explain(error: unknown) {
  return error instanceof Error && !(error instanceof TypeError) ? error.message : "Не удалось связаться с сервером.";
}
