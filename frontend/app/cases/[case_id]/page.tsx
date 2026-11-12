import { CaseDetailPage } from '@/features/cases/case-detail-page';

export default async function CasePage({
  params,
}: {
  params: Promise<{ case_id: string }>;
}) {
  const { case_id: caseId } = await params;
  return <CaseDetailPage key={caseId} caseId={caseId} />;
}
