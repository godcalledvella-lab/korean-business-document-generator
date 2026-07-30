import PreviewWorkspace from "@/components/PreviewWorkspace";

export default async function PreviewPage({
  params,
}: {
  params: Promise<{ sessionId: string }>;
}) {
  const { sessionId } = await params;
  return <PreviewWorkspace sessionId={sessionId} />;
}
