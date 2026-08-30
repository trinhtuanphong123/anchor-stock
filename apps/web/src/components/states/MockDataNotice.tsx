import { Notice } from "./Notice";

/**
 * The local-fixtures banner. Only reachable in development with no API configured: a deployed
 * build never assembles mock data, it renders an error instead.
 *
 * It exists because an unlabelled mock is indistinguishable from a working backend — the numbers
 * look plausible, the charts draw, and nothing on screen says the figures were invented. Its
 * tone is `info` rather than `stale`, so it does not read as a claim about how old real data is.
 */
export function MockDataNotice({ isMock }: { isMock: boolean }) {
  if (!isMock) return null;
  return (
    <Notice tone="mock" label="Dữ liệu giả lập:">
      Chưa cấu hình <code>NEXT_PUBLIC_API_BASE_URL</code>, nên trang đang hiển thị fixture cục bộ
      — không phải số liệu thật từ Supabase.
    </Notice>
  );
}
