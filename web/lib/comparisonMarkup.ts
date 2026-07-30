import type { InvoiceItem } from "@/lib/types";

export const DEFAULT_COMPARISON_MARKUP_PERCENTAGE = 8;
export const QUICK_COMPARISON_MARKUPS = [5, 6, 7, 8, 9, 10] as const;

export type MarkupValidation = {
  value?: number;
  error?: string;
};

export function validateMarkupPercentage(value: unknown): MarkupValidation {
  if (value === null || value === undefined || value === "") {
    return { error: "비교견적서 가산율을 입력해 주세요." };
  }
  const text = typeof value === "number" ? String(value) : value;
  if (
    typeof text !== "string" ||
    !/^(?:\d+(?:\.\d*)?|\.\d+)$/.test(text.trim())
  ) {
    return { error: "가산율은 숫자로 입력해 주세요." };
  }
  const numeric = Number(text);
  if (!Number.isFinite(numeric)) {
    return { error: "가산율은 유효한 숫자여야 합니다." };
  }
  if (numeric < 0 || numeric > 100) {
    return { error: "가산율은 0%에서 100% 사이여야 합니다." };
  }
  return { value: numeric };
}

export function comparisonSupplyAmount(
  items: InvoiceItem[],
  markupPercentage: number,
): number {
  return items.reduce((total, item) => {
    if (
      typeof item.unit_price !== "number" ||
      !Number.isFinite(item.unit_price) ||
      typeof item.quantity !== "number" ||
      !Number.isFinite(item.quantity)
    ) {
      return total;
    }
    const unitPrice = Math.round(
      item.unit_price * (1 + markupPercentage / 100),
    );
    return total + Math.round(unitPrice * item.quantity);
  }, 0);
}
