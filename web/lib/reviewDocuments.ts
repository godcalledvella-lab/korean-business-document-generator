import type { InvoiceDraft } from "@/lib/types";

export const REVIEW_SETTINGS_EXTENSION = "rmntc.review_settings";

export type VisibilityField = {
  value: string;
  visible: boolean;
};

export type ReviewDocumentSettings = {
  statement: {
    sender: string;
    companyName: string;
    bank: string;
    accountNumber: string;
  };
  blueQuotation: {
    client: string;
    product: string;
    showProductDetails: boolean;
    productDetails: string;
    showRemark: boolean;
    remark: string;
    informationBar: {
      companyName: VisibilityField;
      businessNumber: VisibilityField;
      address: VisibilityField;
      representative: VisibilityField;
    };
    footer: {
      telephone: string;
      email: string;
      bank: string;
      accountNumber: string;
    };
  };
  greenQuotation: {
    buyerCompany: string;
    quotationDate: string;
    companyProfile: {
      registrationNumber: string;
      companyName: string;
      representative: string;
      address: string;
      businessType: string;
      businessItem: string;
      phone: string;
      hp: string;
    };
  };
};

export function defaultReviewDocumentSettings(
  draft: InvoiceDraft,
  confidences: Record<string, number> = {},
): ReviewDocumentSettings {
  const descriptions = draft.document.items
    .map((item) => item.description || "")
    .filter(Boolean);
  const product =
    descriptions.length <= 1
      ? descriptions[0] || ""
      : `${descriptions[0]} 외 ${descriptions.length - 1}건`;
  const seller = draft.document.seller;
  const confidentSellerName = confidentText(
    seller.name,
    confidences["document.seller.name"],
  );
  const knownRmntc = isKnownRmntcSeller(seller, confidences);
  const templateCompanyName = "로맨틱어스";
  const statementCompanyName = confidentSellerName || templateCompanyName;
  return {
    statement: {
      sender: statementCompanyName,
      companyName: statementCompanyName,
      bank: "신한은행",
      accountNumber: "110-427-856988",
    },
    blueQuotation: {
      client: `${draft.document.buyer.name || ""} 귀하`.trim(),
      product,
      showProductDetails: true,
      productDetails: descriptions.join(", "),
      showRemark: true,
      remark: "VAT 별도",
      informationBar: {
        companyName: visible(
          knownRmntc
            ? confidentText(seller.name, confidences["document.seller.name"])
            : templateCompanyName,
        ),
        businessNumber: visible(
          knownRmntc
            ? confidentText(
                seller.business_registration_number,
                confidences["document.seller.business_registration_number"],
              )
            : "102-21-34572",
        ),
        address: visible(
          knownRmntc
            ? confidentText(
                seller.address,
                confidences["document.seller.address"],
              )
            : "경상남도 창원시 성산구 외동반림로126번길 57, 1층",
        ),
        representative: visible(
          knownRmntc
            ? confidentText(
                seller.representative,
                confidences["document.seller.representative"],
              )
            : "정성우",
        ),
      },
      footer: {
        telephone:
          knownRmntc
            ? confidentText(
                seller.contact?.phone,
                confidences["document.seller.contact.phone"],
              ) || "010-8579-0342"
            : "010-8579-0342",
        email:
          knownRmntc
            ? confidentText(
                seller.contact?.email,
                confidences["document.seller.contact.email"],
              ) || "rmntcearth@gmail.com"
            : "rmntcearth@gmail.com",
        bank: "신한은행",
        accountNumber: "110-427-856988",
      },
    },
    greenQuotation: {
      buyerCompany: draft.document.buyer.name || "",
      quotationDate: draft.document.dates.issue_date || "",
      companyProfile: {
        registrationNumber: "214-89-07571",
        companyName: "우현코퍼레이션",
        representative: "한주호",
        address: "부산광역시",
        businessType: "제조업",
        businessItem: "OEM ODM 제조",
        phone: "010-4480-7709",
        hp: "010-4480-7709",
      },
    },
  };
}

export function mergeReviewDocumentSettings(
  defaults: ReviewDocumentSettings,
  stored: unknown,
): ReviewDocumentSettings {
  if (!stored || typeof stored !== "object" || Array.isArray(stored)) {
    return defaults;
  }
  const value = stored as Partial<ReviewDocumentSettings>;
  return {
    statement: {
      ...defaults.statement,
      ...(value.statement || {}),
    },
    blueQuotation: {
      ...defaults.blueQuotation,
      ...(value.blueQuotation || {}),
      informationBar: {
        ...defaults.blueQuotation.informationBar,
        ...(value.blueQuotation?.informationBar || {}),
      },
      footer: {
        ...defaults.blueQuotation.footer,
        ...(value.blueQuotation?.footer || {}),
      },
    },
    greenQuotation: {
      ...defaults.greenQuotation,
      ...(value.greenQuotation || {}),
      companyProfile: {
        ...defaults.greenQuotation.companyProfile,
        ...(value.greenQuotation?.companyProfile || {}),
      },
    },
  };
}

function visible(value: unknown): VisibilityField {
  return {
    value: typeof value === "string" ? value : "",
    visible: true,
  };
}

function confidentText(value: unknown, confidence: unknown): string {
  return typeof value === "string" &&
    value.trim() !== "" &&
    typeof confidence === "number" &&
    confidence >= 0.8
    ? value
    : "";
}

function isKnownRmntcSeller(
  seller: InvoiceDraft["document"]["seller"],
  confidences: Record<string, number>,
): boolean {
  const name = confidentText(
    seller.name,
    confidences["document.seller.name"],
  )
    .replace(/\s+/g, "")
    .toLowerCase();
  const registration = confidentText(
    seller.business_registration_number,
    confidences["document.seller.business_registration_number"],
  ).replace(/\D/g, "");
  return (
    registration === "1022134572" ||
    name.includes("로맨틱어스") ||
    name.includes("알엠엔티씨") ||
    name.includes("rmntc")
  );
}
