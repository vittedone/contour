import Report from "./report";

export default async function Page({ searchParams }: {
  searchParams: Promise<{ id?: string; version?: string }>;
}) {
  const { id, version } = await searchParams;
  return <Report key={id} id={id ?? ""} version={version} />;
}
