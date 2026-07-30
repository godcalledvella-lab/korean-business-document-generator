import ReviewWorkspace from "@/components/ReviewWorkspace";

export default async function ReviewPage({
  params,
}: {
  params: Promise<{ sessionId: string }>;
}) {
  const { sessionId } = await params;
  return <ReviewWorkspace sessionId={sessionId} />;
}
