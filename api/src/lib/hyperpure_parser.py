"""Parser for Zomato Hyperpure challan and invoice PDFs.

Uses pdfplumber to extract line items from challan and invoice tables.

Supports two PDF types:
  - Challan: single-page with category headers, pre-tax totals, discounts
  - Invoice (TAX INVOICE): may be multi-page combined PDF; only TAX INVOICE
    pages are parsed (BILL OF SUPPLY pages are ignored). No pre-tax/discount
    columns; tax rate/amount use CGST+SGST+IGST format.

The main entry point parse_hyperpure_pdf auto-detects the type.
"""

import io
import re

import pdfplumber


# Rows to exclude from line items
_EXCLUDED_DESCRIPTIONS = {"delivery charge", "delivery charges", "tcs u/s 206c(1h)", "small order charge"}
_EXCLUDED_HSN = {"996819", "999799"}
# Summary rows to skip entirely (not charges, just totals)
_SUMMARY_DESCRIPTIONS = {"total"}

# Category headers are rows where most cells are empty
_CATEGORY_HEADER_PATTERN = re.compile(
    r"^(bakery|chocolates|dairy|frozen|instant|fruits|vegetables|sauces|seasoning|"
    r"other charges|beverages|grocery|staples|packaging|disposable|cleaning|"
    r"meat|seafood|snacks|ready to|oils|ghee)",
    re.IGNORECASE,
)


def parse_hyperpure_pdf(pdf_bytes: bytes) -> dict:
    """Parse a Hyperpure PDF (auto-detects challan vs invoice).

    Args:
        pdf_bytes: Raw PDF file content.

    Returns:
        dict with keys: billMeta, lineItems, ignoredLines, totals
    """
    pdf = pdfplumber.open(io.BytesIO(pdf_bytes))

    if not pdf.pages:
        pdf.close()
        raise ValueError("PDF has no pages")

    # Auto-detect: check first page text for invoice indicators
    first_page_text = pdf.pages[0].extract_text() or ""
    is_invoice = "TAX INVOICE" in first_page_text.upper() or "BILL OF SUPPLY" in first_page_text.upper()
    pdf.close()

    if is_invoice:
        return parse_hyperpure_invoice_pdf(pdf_bytes)

    return _parse_hyperpure_challan_pdf(pdf_bytes)


def _parse_hyperpure_challan_pdf(pdf_bytes: bytes) -> dict:
    """Parse a Hyperpure challan PDF and return structured bill data."""
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

        # Skip summary rows (e.g. "Total") — not a charge, just a subtotal
        if description_lower in _SUMMARY_DESCRIPTIONS:
            continue

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


# ---------------------------------------------------------------------------
# Invoice (TAX INVOICE) parser
# ---------------------------------------------------------------------------


def parse_hyperpure_invoice_pdf(pdf_bytes: bytes) -> dict:
    """Parse a Hyperpure invoice PDF and return structured bill data.

    Only processes pages marked as TAX INVOICE. BILL OF SUPPLY pages are
    ignored. If no TAX INVOICE page is found, raises ValueError.

    Returns:
        dict with keys: billMeta, lineItems, ignoredLines, totals
    """
    pdf = pdfplumber.open(io.BytesIO(pdf_bytes))

    if not pdf.pages:
        pdf.close()
        raise ValueError("PDF has no pages")

    # Find the first TAX INVOICE page
    invoice_page = None
    for page in pdf.pages:
        text = page.extract_text() or ""
        if "TAX INVOICE" in text.upper():
            invoice_page = page
            break

    if invoice_page is None:
        pdf.close()
        raise ValueError("No TAX INVOICE page found in PDF")

    full_text = invoice_page.extract_text() or ""
    bill_meta = _extract_invoice_meta(full_text)

    tables = invoice_page.extract_tables()
    if not tables:
        pdf.close()
        raise ValueError("No tables found in invoice PDF")

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
        if any(c in ("s no.", "s no", "sl no.", "si no.", "si\nno.") for c in cells):
            col_map = _detect_invoice_column_map(cells)
            break

    for row in main_table:
        if not row or all(not cell or not str(cell).strip() for cell in row):
            continue

        cells = [str(c).strip() if c else "" for c in row]

        # Skip header row
        if cells[0].lower() in ("s no.", "s no", "sl no.", "si no.", "si\nno."):
            continue

        # Skip section headers like "Other Charges"
        non_empty = [c for c in cells if c]
        if len(non_empty) <= 2:
            combined = " ".join(non_empty)
            if _CATEGORY_HEADER_PATTERN.match(combined):
                continue
            if not any(c.replace(".", "").replace(",", "").isdigit() for c in non_empty):
                continue

        parsed = _parse_invoice_line_item_row(cells, col_map)
        if not parsed:
            continue

        description_lower = parsed["description"].lower().strip()

        if description_lower in _SUMMARY_DESCRIPTIONS:
            continue

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

    items_total = sum(i.get("total", 0) for i in line_items)
    other_charges = sum(il.get("total", 0) for il in ignored_lines)
    totals = {
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


def _extract_invoice_meta(text: str) -> dict:
    """Extract bill metadata from an invoice page's text.

    The header layout is typically two lines:
      Invoice Number  Order No.  Invoice Date  Reference PO
      ZHPHR27-00179182  ZHPHR27-OR-0028523511  25 Jul 2026  -
    """
    meta = {
        "invoiceNumber": None,
        "orderNo": None,
        "invoiceDate": None,
        "supplier": "Zomato Hyperpure",
        "documentType": "invoice",
    }

    # Match the two-line header pattern
    m = re.search(
        r"Invoice\s*Number\s+Order\s*No\.?\s+Invoice\s*Date.*?\n"
        r"\s*(\S+)\s+(ZHPHR\S+)\s+(\d{1,2}\s+\w{3,9}\s+\d{4})",
        text, re.IGNORECASE,
    )
    if m:
        meta["invoiceNumber"] = m.group(1)
        meta["orderNo"] = m.group(2)
        meta["invoiceDate"] = m.group(3)
    else:
        # Fallback: try individual patterns
        m = re.search(r"\n\s*(Z[A-Z]PHR\d+-\d+)\s+", text)
        if m:
            meta["invoiceNumber"] = m.group(1)

        m = re.search(r"(ZHPHR\d+-OR-\d+)", text)
        if m:
            meta["orderNo"] = m.group(1)

        date_pattern = r"(\d{1,2}\s+\w{3,9}\s+\d{4})"
        m = re.search(r"Invoice\s*Date.*?" + date_pattern, text, re.IGNORECASE | re.DOTALL)
        if m:
            meta["invoiceDate"] = m.group(1)

    return meta


def _detect_invoice_column_map(header_cells: list[str]) -> dict:
    """Detect column indices from an invoice header row."""
    col_map = {}
    for i, cell in enumerate(header_cells):
        c = cell.lower().replace("\n", " ").strip()
        if c in ("s no.", "s no", "sl no.", "si no.", "si no"):
            col_map["s_no"] = i
        elif "description" in c:
            col_map["description"] = i
        elif c == "hsn":
            col_map["hsn"] = i
        elif "qty" in c:
            col_map["qty"] = i
        elif "unit price" in c:
            col_map["unit_price"] = i
        elif c in ("uom", "uom "):
            col_map["uom"] = i
        elif "taxable" in c:
            col_map["taxable"] = i
        elif "tax rate" in c:
            col_map["tax_rate"] = i
        elif "tax amount" in c:
            col_map["tax_amount"] = i
        elif c == "total":
            col_map["total"] = i
    return col_map


def _parse_invoice_line_item_row(cells: list[str], col_map: dict | None = None) -> dict | None:
    """Parse an invoice table row as a line item.

    Invoice columns: S No. | Description | HSN | Qty | Unit Price | UoM |
    Taxable Amount | Tax Rate (CGST+SGS T+IGST)% | Tax Amount (CGST+SGS T+IGST) | Total
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
        description = cell_at(col_map.get("description"))

        # If description col is empty, try walking forward from s_no
        if not description and col_map.get("s_no") is not None:
            si_idx = col_map["s_no"]
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
        taxable_amount = to_float(cell_at(col_map.get("taxable")))
        tax_rate_str = cell_at(col_map.get("tax_rate")).strip()
        tax_amount_str = cell_at(col_map.get("tax_amount")).strip()
        total = to_float(cell_at(col_map.get("total")))
    else:
        # Fallback: positional parsing
        non_empty = [c for c in cells if c]
        if len(non_empty) < 8:
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
            taxable_amount = to_float(remaining[4])
            tax_rate_str = (remaining[5] or "").strip()
            tax_amount_str = (remaining[6] or "").strip()
            total = to_float(remaining[7])
        except IndexError:
            return None

    # Must have meaningful numeric data
    if quantity == 0 and unit_price == 0 and total == 0:
        return None

    tax_rate = _parse_tax_rate(tax_rate_str)
    tax_amount = _parse_invoice_tax_amount(tax_amount_str)

    return {
        "description": description.strip(),
        "hsnCode": hsn_code if hsn_code else None,
        "quantity": quantity,
        "unitPrice": unit_price,
        "uom": uom if uom else None,
        "taxableAmount": taxable_amount,
        "taxRate": tax_rate,
        "taxAmount": tax_amount,
        "total": total,
    }


def _parse_invoice_tax_amount(amount_str: str) -> float:
    """Parse invoice tax amount string like '6.1+6.1+0' into a total."""
    if not amount_str:
        return 0.0

    parts = amount_str.split("+")
    total = 0.0
    for part in parts:
        try:
            total += float(part.strip())
        except ValueError:
            pass
    return round(total, 2)
