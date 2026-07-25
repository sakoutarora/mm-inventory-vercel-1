"""Parser for Zomato Hyperpure challan PDFs.

Uses pdfplumber to extract line items from the challan table.
Only page 1 contains data; page 2 is a legal footer.

Layout (top to bottom):
  1. Header area — Order No, delivery time slot
  2. Shipping info — warehouse, customer outlet, GSTINs
  3. Metadata row — Invoice Date, Order Date, Reference PO, Payment Status
  4. Line items table — the main data (with inline category headers)
  5. Other Charges — Delivery Charge + TCS (excluded)
  6. Totals row
  7. Tax breakdown
  8. Challan verified by
"""

import io
import re

import pdfplumber


# Rows to exclude from line items
_EXCLUDED_DESCRIPTIONS = {"delivery charge", "tcs u/s 206c(1h)", "small order charge", "total"}
_EXCLUDED_HSN = {"996819", "999799"}

# Category headers are rows where most cells are empty
_CATEGORY_HEADER_PATTERN = re.compile(
    r"^(bakery|chocolates|dairy|frozen|instant|fruits|vegetables|sauces|seasoning|"
    r"other charges|beverages|grocery|staples|packaging|disposable|cleaning|"
    r"meat|seafood|snacks|ready to|oils|ghee)",
    re.IGNORECASE,
)


def parse_hyperpure_pdf(pdf_bytes: bytes) -> dict:
    """Parse a Hyperpure challan PDF and return structured bill data.

    Args:
        pdf_bytes: Raw PDF file content.

    Returns:
        dict with keys: billMeta, lineItems, ignoredLines, totals
    """
    pdf = pdfplumber.open(io.BytesIO(pdf_bytes))

    if not pdf.pages:
        raise ValueError("PDF has no pages")

    page = pdf.pages[0]
    full_text = page.extract_text() or ""

    # Extract bill metadata from header text
    bill_meta = _extract_meta(full_text)

    # Extract tables
    tables = page.extract_tables()
    if not tables:
        raise ValueError("No tables found in PDF")

    # Find the main line items table (usually the largest one)
    main_table = max(tables, key=len)

    line_items = []
    ignored_lines = []
    sl_no = 0

    # Detect column layout from the header row
    col_map = None
    for row in main_table:
        if not row:
            continue
        cells = [str(c).strip().lower() if c else "" for c in row]
        if any(c in ("si\nno.", "si no.", "sl no.", "sl no", "s.no", "s.no.") for c in cells):
            col_map = _detect_column_map(cells)
            break

    for row in main_table:
        if not row or all(not cell or not str(cell).strip() for cell in row):
            continue

        # Clean cells — keep None positions as empty strings
        cells = [str(c).strip() if c else "" for c in row]

        # Skip header row
        if cells[0].lower() in ("si no.", "si no", "sl no.", "sl no", "s.no", "s.no.", "si\nno."):
            continue

        # Skip category header rows (single text spanning the row)
        non_empty = [c for c in cells if c]
        if len(non_empty) <= 2:
            combined = " ".join(non_empty)
            if _CATEGORY_HEADER_PATTERN.match(combined):
                continue
            # Also skip if it's clearly not a data row (no numbers)
            if not any(c.replace(".", "").replace(",", "").isdigit() for c in non_empty):
                continue

        # Try to parse as a line item row
        parsed = _parse_line_item_row(cells, col_map)
        if not parsed:
            continue

        description_lower = parsed["description"].lower().strip()

        # Check exclusions
        if description_lower in _EXCLUDED_DESCRIPTIONS:
            ignored_lines.append({
                "description": parsed["description"],
                "total": parsed.get("total", 0),
                "reason": "Non-inventory charge",
            })
            continue

        if parsed.get("hsnCode") in _EXCLUDED_HSN:
            ignored_lines.append({
                "description": parsed["description"],
                "total": parsed.get("total", 0),
                "reason": "Non-inventory charge",
            })
            continue

        sl_no += 1
        parsed["slNo"] = sl_no
        line_items.append(parsed)

    # Calculate totals (grandTotal includes non-inventory charges like delivery, TCS)
    items_total = sum(i.get("total", 0) for i in line_items)
    other_charges = sum(il.get("total", 0) for il in ignored_lines)
    totals = {
        "subtotal": sum(i.get("preTaxTotal", 0) for i in line_items),
        "totalDiscount": sum(i.get("discount", 0) for i in line_items),
        "taxableAmount": sum(i.get("taxableAmount", 0) for i in line_items),
        "taxAmount": sum(i.get("taxAmount", 0) for i in line_items),
        "itemsTotal": items_total,
        "otherCharges": other_charges,
        "grandTotal": items_total + other_charges,
    }

    pdf.close()

    return {
        "billMeta": bill_meta,
        "lineItems": line_items,
        "ignoredLines": ignored_lines,
        "totals": totals,
    }


def _extract_meta(text: str) -> dict:
    """Extract bill metadata from the full page text."""
    meta = {
        "orderNo": None,
        "invoiceDate": None,
        "orderDate": None,
        "supplier": "Zomato Hyperpure",
        "paymentStatus": "unpaid",
    }

    # Order No
    m = re.search(r"Order\s*No[.:]?\s*(ZHPHR\S+)", text, re.IGNORECASE)
    if m:
        meta["orderNo"] = m.group(1)

    # Dates may be on a separate line from labels.
    # Pattern: "Invoice Date ... Order Date ..." then "22 Jul 2026 21 Jul 2026 ..."
    date_pattern = r"(\d{1,2}\s+\w{3,9}\s+\d{4})"
    m = re.search(
        r"Invoice\s*Date.*?Order\s*Date.*?\n\s*" + date_pattern + r"\s+" + date_pattern,
        text, re.IGNORECASE,
    )
    if m:
        meta["invoiceDate"] = m.group(1)
        meta["orderDate"] = m.group(2)
    else:
        # Fallback: inline format
        m = re.search(r"Invoice\s*Date[:\s]*\n?\s*" + date_pattern, text, re.IGNORECASE)
        if m:
            meta["invoiceDate"] = m.group(1)
        m = re.search(r"Order\s*Date[:\s]*\n?\s*" + date_pattern, text, re.IGNORECASE)
        if m:
            meta["orderDate"] = m.group(1)

    # Payment Status
    m = re.search(r"Payment\s*Status[:\s]*(unpaid|paid)", text, re.IGNORECASE)
    if m:
        meta["paymentStatus"] = m.group(1).lower()

    return meta


def _detect_column_map(header_cells: list[str]) -> dict:
    """Detect column indices from the header row.

    Returns a dict mapping field names to column indices.
    """
    col_map = {}
    for i, cell in enumerate(header_cells):
        c = cell.lower().replace("\n", " ").strip()
        if c in ("si no.", "si no", "sl no.", "sl no", "s.no", "s.no."):
            col_map["si_no"] = i
        elif "description" in c:
            col_map["description"] = i
        elif c == "hsn":
            col_map["hsn"] = i
        elif "qty" in c:
            col_map["qty"] = i
        elif "unit price" in c:
            col_map["unit_price"] = i
        elif c == "uom" or c == "uom ":
            col_map["uom"] = i
        elif "pre tax" in c:
            col_map["pre_tax"] = i
        elif "discou" in c or "discount" in c:
            col_map["discount"] = i
        elif "taxable" in c:
            col_map["taxable"] = i
        elif "tax rate" in c:
            col_map["tax_rate"] = i
        elif "total tax" in c:
            col_map["tax_amount"] = i
        elif c == "total":
            col_map["total"] = i
    return col_map


def _parse_line_item_row(cells: list[str], col_map: dict | None = None) -> dict | None:
    """Try to parse a table row as a line item.

    Expected column order:
    SI No | Description | HSN | Inv. Qty | Unit Price | UoM |
    Pre Tax Total | Discount | Taxable Amount | Tax Rate | Total Tax | Total
    """

    def to_float(s):
        if not s:
            return 0.0
        s = s.replace(",", "").replace(" ", "").strip()
        try:
            return float(s)
        except ValueError:
            return 0.0

    def cell_at(idx):
        if idx is not None and idx < len(cells):
            return cells[idx]
        return ""

    if col_map:
        # Use detected column positions
        description = cell_at(col_map.get("description"))

        # If description col is empty, try using col after si_no
        if not description and col_map.get("si_no") is not None:
            si_idx = col_map["si_no"]
            # Walk forward to find first non-empty cell after si_no
            for k in range(si_idx + 1, min(si_idx + 4, len(cells))):
                if cells[k]:
                    description = cells[k]
                    break

        if not description or len(description) < 3:
            return None

        hsn_raw = cell_at(col_map.get("hsn"))
        hsn_code = re.sub(r"\s+", "", hsn_raw)

        quantity = to_float(cell_at(col_map.get("qty")))
        unit_price = to_float(cell_at(col_map.get("unit_price")))
        uom = cell_at(col_map.get("uom")).strip()
        pre_tax_total = to_float(cell_at(col_map.get("pre_tax")))
        discount = to_float(cell_at(col_map.get("discount")))
        taxable_amount = to_float(cell_at(col_map.get("taxable")))
        tax_rate_str = cell_at(col_map.get("tax_rate")).strip()
        tax_amount = to_float(cell_at(col_map.get("tax_amount")))
        total = to_float(cell_at(col_map.get("total")))
    else:
        # Fallback: strip None/empty cells and use positional parsing
        non_empty = [c for c in cells if c]
        if len(non_empty) < 10:
            return None

        si_str = non_empty[0].replace(",", "").strip()
        if si_str and si_str.replace(".", "").isdigit():
            description = non_empty[1]
            remaining = non_empty[2:]
        else:
            description = non_empty[0]
            remaining = non_empty[1:]

        if not description or len(description) < 3:
            return None

        hsn_raw = remaining[0] if remaining else ""
        hsn_code = re.sub(r"\s+", "", hsn_raw)

        try:
            quantity = to_float(remaining[1])
            unit_price = to_float(remaining[2])
            uom = (remaining[3] or "").strip()
            pre_tax_total = to_float(remaining[4])
            discount = to_float(remaining[5])
            taxable_amount = to_float(remaining[6])
            tax_rate_str = (remaining[7] or "").strip()
            tax_amount = to_float(remaining[8])
            total = to_float(remaining[9])
        except IndexError:
            return None

    # Must have meaningful numeric data
    if quantity == 0 and unit_price == 0 and total == 0:
        return None

    # Parse tax rate string "2.5+2.5+0+0" into component rates
    tax_rate = _parse_tax_rate(tax_rate_str)

    return {
        "description": description.strip(),
        "hsnCode": hsn_code if hsn_code else None,
        "quantity": quantity,
        "unitPrice": unit_price,
        "uom": uom if uom else None,
        "preTaxTotal": pre_tax_total,
        "discount": discount,
        "taxableAmount": taxable_amount,
        "taxRate": tax_rate,
        "taxAmount": tax_amount,
        "total": total,
    }


def _parse_tax_rate(rate_str: str) -> dict:
    """Parse tax rate string like '2.5+2.5+0+0' into component rates."""
    result = {"cgst": 0.0, "sgst": 0.0, "igst": 0.0, "cess": 0.0}

    if not rate_str:
        return result

    # Remove % sign if present
    rate_str = rate_str.replace("%", "").strip()

    parts = rate_str.split("+")
    keys = ["cgst", "sgst", "igst", "cess"]

    for i, key in enumerate(keys):
        if i < len(parts):
            try:
                result[key] = float(parts[i].strip())
            except ValueError:
                pass

    return result
