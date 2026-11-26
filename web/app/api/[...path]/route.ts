import type { NextRequest } from "next/server";

type Context = { params: Promise<{ path: string[] }> };

async function forward(request: NextRequest, { params }: Context) {
  const { path } = await params;
  const route = path.join("/");
  if (!/^research(?:\/[0-9a-f-]{36}\/(?:sources(?:\/[0-9a-f-]{36}\/fragments)?|pdf|links|analysis|reports|evidence))?$/.test(route)) {
    return Response.json({ detail: "Страница не найдена." }, { status: 404 });
  }
  const headers = new Headers();
  const type = request.headers.get("content-type");
  if (type) headers.set("content-type", type);
  const options: RequestInit & { duplex: "half" } = {
    method: request.method, body: request.body, duplex: "half",
    headers, cache: "no-store", redirect: "error", signal: request.signal,
  };
  try {
    const upstream = await fetch(
      `${process.env.API_ORIGIN ?? "http://localhost:8000"}/${route}${request.nextUrl.search}`,
      options,
    );
    return new Response(upstream.body, {
      status: upstream.status,
      headers: { "Content-Type": "application/json", "Cache-Control": "no-store" },
    });
  } catch {
    return Response.json({ detail: "Сервис временно недоступен." }, { status: 503 });
  }
}

export { forward as GET, forward as POST };
