"use client";

import { useActiveModelRun } from "@/hooks/dashboard";
import { coverageFbarAdjusted, type ActiveModelRunResponse } from "@/lib/api";
import { DefinitionList, DocPanel, type DefinitionItem } from "@/components/ds";
import { ErrorState, LoadingState } from "@/components/states";
import { DASH, formatDecimal, formatInt, formatParamDate } from "@/components/market/format";
import styles from "./About.module.css";

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
 *
 * **The only screen in the product with running prose**, which is why `as-prose` exists and why
 * it caps the measure: three panels of full-width 1440px lines would be unreadable beside three
 * screens of tables. The wording is unchanged from the copy this page has always carried.
 */
export default function AboutPage() {
  return (
    <div className={styles.screen}>
      <DocPanel label="Hệ thống này là gì">
        <h2 className="as-panel__title">Hệ thống này là gì</h2>
        <div className="as-prose">
          <p>
            Trang này theo dõi <strong>85 cổ phiếu HOSE</strong> và chỉ ra{" "}
            <strong>10 mã điểm neo</strong> đại diện cho cả rổ. Mỗi mã còn lại được gán về một điểm
            neo — mã có diễn biến giá tương đồng nhất với nó sau khi đã loại bỏ phần biến động
            chung của toàn thị trường.
          </p>
          <p>
            Tập điểm neo được tính sẵn theo định kỳ và{" "}
            <strong>không tính lại theo từng phiên</strong>. Giá, khối lượng và các chỉ báo kỹ
            thuật thì cập nhật đến phiên gần nhất thu thập được. Vì vậy ngày của mô hình và ngày
            của giá không trùng nhau — cả hai đều được ghi rõ ở chân mỗi trang.
          </p>
          <p>
            Giá sử dụng là <strong>giá điều chỉnh</strong>, nên biểu đồ ở đây có thể lệch so với
            biểu đồ giá thô của công ty chứng khoán quanh ngày giao dịch không hưởng quyền.
          </p>
        </div>
      </DocPanel>

      <DocPanel label="Những gì trang này không làm">
        <h2 className="as-panel__title">Những gì trang này không làm</h2>
        <div className="as-prose">
          <p>
            Đây là công cụ trình bày số liệu đã tính sẵn. Trang này{" "}
            <strong>không dự báo giá</strong>, <strong>không đưa ra khuyến nghị mua bán</strong>,
            không tính xác suất và không đề xuất tỷ trọng danh mục. Các nhận định trong phần
            &ldquo;Phân tích kỹ thuật&rdquo; là mô tả trạng thái của những con số đã lưu, không
            phải lời khuyên đầu tư.
          </p>
        </div>
      </DocPanel>

      <RunParameters />
    </div>
  );
}

/**
 * The thirteen figures that identify the run being served.
 *
 * **Four-digit years here and nowhere else.** Every other date in the product is `DD/MM/YY`,
 * because a session label sits in a column and the century is never in question. This table is
 * the one place where the year boundary IS the subject — a reviewer reads it to know which window
 * the estimate came from — so it takes `formatParamDate`.
 *
 * `DefinitionList` rather than a table, and its terms are not uppercased: these labels carry
 * Greek, and `text-transform: uppercase` renders τ as Τ, which reads as a Latin T and names a
 * threshold that does not exist.
 */
function RunParameters() {
  const state = useActiveModelRun();

  return (
    <DocPanel label="Tham số của lần chạy đang dùng">
      <h2 className="as-panel__title">Tham số của lần chạy đang dùng</h2>
      {state.kind === "loading" && <LoadingState rows={3} label="Đang tải tham số" />}
      {state.kind === "error" && <ErrorState code={state.code} message={state.message} />}
      {state.kind === "data" && <DefinitionList items={parameterItems(state.data)} />}
    </DocPanel>
  );
}

function parameterItems(run: ActiveModelRunResponse): DefinitionItem[] {
  return [
    {
      label: "Cửa sổ ước lượng",
      value: `${formatParamDate(run.window_start)} – ${formatParamDate(run.window_end)}`,
    },
    { label: "Số phiên", value: formatInt(run.n_sessions) },
    { label: "Phiên dữ liệu mới nhất", value: formatParamDate(run.latest_session) },
    { label: "Số mã trong rổ", value: formatInt(run.n_tickers) },
    { label: "Số điểm neo công bố (k)", value: formatInt(run.k) },
    { label: "Số bước đã chạy (k_max)", value: formatInt(run.k_max) },
    { label: "Ngưỡng τ", value: formatDecimal(run.tau) },
    { label: "Độ phủ trung bình F̄(S)", value: formatDecimal(run.coverage_fbar, 4) },
    // Never on its own: F̄ counts each anchor covering itself at ρ²=1 — about 45 % of F here —
    // so the adjusted figure, the coverage actually achieved over the non-anchor tickers, sits
    // immediately beneath it (D-26).
    { label: "Độ phủ đã hiệu chỉnh F̄_adj", value: formatDecimal(coverageFbarAdjusted(run), 4) },
    {
      label: "Số mã dưới τ",
      value: `${formatInt(run.n_under_tau)} / ${formatInt(run.n_tickers)}`,
    },
    { label: "Độ đo tương đồng", value: run.similarity_measure },
    { label: "Chỉ số tham chiếu", value: run.index_symbol },
    { label: "Mã artifact", value: run.artifact_id || DASH },
  ];
}
