import type { InvoiceDraft } from "@/lib/types";
import {
  canonicalStringField,
  canonicalStringFields,
} from "./canonicalSchema.ts";

export type ReviewValidationIssue = {
  path: string;
  message: string;
};

function missingNumber(value: unknown): boolean {
  return typeof value !== "number" || !Number.isFinite(value);
}

function particle(label: string, withFinal: string, withoutFinal: string): string {
  const code = label.charCodeAt(label.length - 1);
  const hasFinal = code >= 0xac00 && code <= 0xd7a3 && (code - 0xac00) % 28 !== 0;
  return hasFinal ? withFinal : withoutFinal;
}

const REQUIRED_RMNTC_STRINGS = new Set([
  "document.seller.business_registration_number",
  "document.seller.representative",
  "document.seller.address",
  "document.seller.business_type",
  "document.seller.business_item",
  "document.seller.contact.email",
]);

export function isRequiredReviewString(
  draft: InvoiceDraft,
  path: string,
): boolean {
  return (
    canonicalStringField(draft, path)?.required === true ||
    REQUIRED_RMNTC_STRINGS.has(path)
  );
}

export function fieldId(path: string): string {
  return `field-${path.replace(/[^a-zA-Z0-9_-]+/g, "-")}`;
}

export function validateCanonicalDraft(
  draft: InvoiceDraft | null,
): ReviewValidationIssue[] {
  if (!draft) return [{ path: "document", message: "검토할 계산서 정보가 없습니다." }];

  const issues: ReviewValidationIssue[] = [];
  const stringField = (
    path: string,
    value: unknown,
    label: string,
    required = isRequiredReviewString(draft, path),
  ) => {
    if (value === undefined || value === null || value === "") {
      if (required) {
        issues.push({
          path,
          message: `${label}${particle(label, "을", "를")} 입력해 주세요.`,
        });
      }
      return;
    }
    if (typeof value !== "string") {
      issues.push({
        path,
        message: `${label}${particle(label, "은", "는")} 문자로 입력해 주세요.`,
      });
      return;
    }
    if (required && value.trim() === "") {
      issues.push({
        path,
        message: `${label}${particle(label, "을", "를")} 입력해 주세요.`,
      });
    }
  };
  const requiredNumber = (path: string, value: unknown, message: string) => {
    if (missingNumber(value)) issues.push({ path, message });
  };

  for (const field of canonicalStringFields(draft)) {
    stringField(
      field.path,
      field.value,
      labelForStringPath(field.path),
      field.required || REQUIRED_RMNTC_STRINGS.has(field.path),
    );
  }

  if (!Array.isArray(draft.document.items) || draft.document.items.length === 0) {
    issues.push({ path: "document.items", message: "품목을 한 개 이상 입력해 주세요." });
  } else {
    draft.document.items.forEach((item, index) => {
      const prefix = `document.items.${index}`;
      const number = index + 1;
      requiredNumber(
        `${prefix}.quantity`,
        item.quantity,
        `품목 ${number}의 수량을 입력해 주세요.`,
      );
      requiredNumber(
        `${prefix}.unit_price`,
        item.unit_price,
        `품목 ${number}의 단가를 입력해 주세요.`,
      );
      requiredNumber(
        `${prefix}.supply_amount`,
        item.supply_amount,
        `품목 ${number}의 공급가액을 입력해 주세요.`,
      );
      requiredNumber(
        `${prefix}.vat`,
        item.vat,
        `품목 ${number}의 세액을 입력해 주세요.`,
      );
      requiredNumber(
        `${prefix}.total`,
        item.total,
        `품목 ${number}의 합계금액을 입력해 주세요.`,
      );
    });
  }

  requiredNumber(
    "document.totals.supply_amount",
    draft.document.totals?.supply_amount,
    "공급가액 합계를 입력해 주세요.",
  );
  requiredNumber(
    "document.totals.vat",
    draft.document.totals?.vat,
    "세액 합계를 입력해 주세요.",
  );
  requiredNumber(
    "document.totals.total",
    draft.document.totals?.total,
    "총 합계금액을 입력해 주세요.",
  );
  return issues;
}

function labelForStringPath(path: string): string {
  const item = path.match(/^document\.items\.(\d+)\.(description|unit|remarks)$/);
  if (item) {
    const labels = {
      description: "품목명",
      unit: "단위",
      remarks: "비고",
    };
    return `품목 ${Number(item[1]) + 1}의 ${labels[item[2] as keyof typeof labels]}`;
  }
  const labels: Record<string, string> = {
    schema_version: "스키마 버전",
    document_type: "문서 유형",
    "document.invoice_number": "승인번호",
    "document.dates.issue_date": "작성일자",
    "document.dates.supply_date": "공급일자",
    "document.dates.due_date": "지급기한",
    "document.currency": "통화 코드",
    "document.seller.name": "공급자 상호",
    "document.seller.business_registration_number": "공급자 사업자등록번호",
    "document.seller.representative": "공급자 대표자",
    "document.seller.address": "공급자 주소",
    "document.seller.business_type": "공급자 업태",
    "document.seller.business_item": "공급자 종목",
    "document.seller.contact.name": "공급자 담당자",
    "document.seller.contact.email": "공급자 이메일",
    "document.seller.contact.phone": "공급자 전화번호",
    "document.buyer.name": "공급받는자 상호",
    "document.buyer.business_registration_number": "공급받는자 사업자등록번호",
    "document.buyer.representative": "공급받는자 대표자",
    "document.buyer.address": "공급받는자 주소",
    "document.buyer.business_type": "공급받는자 업태",
    "document.buyer.business_item": "공급받는자 종목",
    "document.buyer.contact.name": "공급받는자 담당자",
    "document.buyer.contact.email": "공급받는자 이메일",
    "document.buyer.contact.phone": "공급받는자 전화번호",
    "document.remarks": "문서 비고",
  };
  return labels[path] || path;
}
