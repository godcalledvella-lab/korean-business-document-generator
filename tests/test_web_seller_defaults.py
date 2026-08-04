from __future__ import annotations

import copy

from web.scripts.extract_invoice import (
    RMNTC_SELLER_DEFAULTS,
    apply_rmntc_seller_defaults,
)


def test_new_review_session_replaces_only_ocr_seller_with_rmntc_defaults():
    buyer = {
        "name": "새 구매자",
        "business_registration_number": "111-22-33333",
    }
    items = [{"description": "새 품목", "quantity": 2}]
    draft = {
        "document": {
            "seller": {
                "name": "OCR 공급자",
                "contact": {"email": "ocr@example.com", "phone": "02-0000-0000"},
            },
            "buyer": copy.deepcopy(buyer),
            "items": copy.deepcopy(items),
        }
    }

    apply_rmntc_seller_defaults(draft)

    assert draft["document"]["seller"] == RMNTC_SELLER_DEFAULTS
    assert draft["document"]["buyer"] == buyer
    assert draft["document"]["items"] == items
    assert draft["document"]["seller"]["contact"]["phone"] == ""


def test_rmntc_default_constant_is_not_mutated_by_session_edits():
    first = {"document": {"seller": {}}}
    second = {"document": {"seller": {}}}
    apply_rmntc_seller_defaults(first)
    first["document"]["seller"]["name"] = "사용자 수정 상호"
    first["document"]["seller"]["contact"]["phone"] = "010-1111-2222"

    apply_rmntc_seller_defaults(second)

    assert second["document"]["seller"] == RMNTC_SELLER_DEFAULTS
