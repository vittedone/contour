import Evidence from "./reader";

type Params = { research?: string; section?: string; start?: string; from?: string; to?: string };

export default async function Page({ searchParams }: { searchParams: Promise<Params> }) {
  const { research = "", section = "", start = "", from, to } = await searchParams;
  return <Evidence research={research} section={section} start={start} from={from} to={to} />;
}
