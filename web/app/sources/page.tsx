import Sources from "./sources";

export default async function Page({ searchParams }: {
  searchParams: Promise<{ id?: string }>;
}) {
  return <Sources selected={(await searchParams).id} />;
}
