"use client";

import { useActiveModelRun } from "@/hooks/dashboard";
import { coverageFbarAdjusted } from "@/lib/api";
import { ErrorState, LoadingState } from "@/components/states";
import ui from "@/components/ui.module.css";
import { DASH, formatDate, formatDecimal, formatInt } from "@/components/market/format";

/**
 * `/about` — Giới thiệu.
 *
 * Replaces the Leiden-era `/methodology` (D-24, S2), which ran to ~300 lines: an "It does / It
 * does not" pair, seven limitations, two verbatim disclaimers, and two charts drawn on fabricated
 * data. `docs/03` §5 says the report is where the method is argued and the dashboard is where it
 * is applied, so that page's content belongs to the report.
 *
 * What could not move here is the disclaimer. `docs/02` §4 forbids this system from making a
 * probabilistic statement, a portfolio weight or a recommendation, and a reader deserves one fixed
 * place where that is stated rather than having to infer it. That is the second section below.
 *
 * The parameter table is the other half: it is where the run identity demoted from the provenance
 * strip actually lives, and it is what a reviewer reproducing the result reads.
 */
export default function AboutPage() {
  const state = useActiveModelRun();

  return (
    <div className={ui.page}>
      <section className={ui.panel}>
        <h2 className={ui.panelTitle}>Hệ thống này là gì</h2>
        <div className={ui.prose}>
          <p>
            Trang này theo dõi <strong>85 cổ phiếu HOSE</strong> và chỉ ra{" "}
            <strong>10 mã điểm neo</strong> đại diện cho cả rổ. Mỗi mã còn lại được gán về một
            điểm neo — mã có diễn biến giá tương đồng nhất với nó sau khi đã loại bỏ phần biến
            động chung của toàn thị trường.
          </p>
          <p>
            Tập điểm neo được tính sẵn theo định kỳ và <strong>không tính lại theo từng phiên</strong>.
            Giá, khối lượng và các chỉ báo kỹ thuật thì cập nhật đến phiên gần nhất thu thập được.
            Vì vậy ngày của mô hình và ngày của giá không trùng nhau — cả hai đều được ghi rõ ở
            chân mỗi trang.
          </p>
          <p>
            Giá sử dụng là <strong>giá điều chỉnh</strong>, nên biểu đồ ở đây có thể lệch so với
            biểu đồ giá thô của công ty chứng khoán quanh ngày giao dịch không hưởng quyền.
          </p>
        </div>
      </section>

      <section className={ui.panel}>
        <h2 className={ui.panelTitle}>Những gì trang này không làm</h2>
        <div className={ui.prose}>
          <p>
            Đây là công cụ trình bày số liệu đã tính sẵn. Trang này{" "}
            <strong>không dự báo giá</strong>, <strong>không đưa ra khuyến nghị mua bán</strong>,
            không tính xác suất và không đề xuất tỷ trọng danh mục. Các nhận định trong phần
            &ldquo;Phân tích kỹ thuật&rdquo; là mô tả trạng thái của những con số đã lưu, không
            phải lời khuyên đầu tư.
          </p>
        </div>
      </section>

      <section className={ui.panel}>
        <h2 className={ui.panelTitle}>Tham số của lần chạy đang dùng</h2>
        {state.kind === "loading" && <LoadingState rows={3} label="Đang tải tham số" />}
        {state.kind === "error" && <ErrorState code={state.code} message={state.message} />}
        {state.kind === "data" && (
          <dl className={ui.defs}>
            {(
              [
                ["Cửa sổ ước lượng", `${formatDate(state.data.window_start)} – ${formatDate(state.data.window_end)}`],
                ["Số phiên", formatInt(state.data.n_sessions)],
                ["Phiên dữ liệu mới nhất", formatDate(state.data.latest_session)],
                ["Số mã trong rổ", formatInt(state.data.n_tickers)],
                ["Số điểm neo công bố (k)", formatInt(state.data.k)],
                ["Số bước đã chạy (k_max)", formatInt(state.data.k_max)],
                ["Ngưỡng τ", formatDecimal(state.data.tau)],
                ["Độ phủ trung bình F̄(S)", formatDecimal(state.data.coverage_fbar, 4)],
                // F̄ counts each anchor covering itself at ρ²=1 — about 45 % of F. The adjusted
                // figure is the coverage actually achieved over the non-anchor tickers (D-26).
                ["Độ phủ đã hiệu chỉnh F̄_adj", formatDecimal(coverageFbarAdjusted(state.data), 4)],
                ["Số mã dưới τ", `${formatInt(state.data.n_under_tau)} / ${formatInt(state.data.n_tickers)}`],
                ["Độ đo tương đồng", state.data.similarity_measure],
                ["Chỉ số tham chiếu", state.data.index_symbol],
                ["Mã artifact", state.data.artifact_id || DASH],
              ] as const
            ).map(([label, value]) => (
              <div key={label}>
                <dt className={ui.defTerm}>{label}</dt>
                <dd className={ui.defValue}>{value}</dd>
              </div>
            ))}
          </dl>
        )}
      </section>
    </div>
  );
}
