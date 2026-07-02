# Phase 2: Extraction Pipeline

## What Gets Built

The complete 7-layer extraction pipeline that transforms raw PDF files into validated rows in Postgres normalized tables and Neo4j graph nodes and relationships. Document type classification for all 8 types in the dataset. Rule-based extraction with label dictionaries for each text-layer document type. Gemini Flash Vision extraction for the 5 image PDFs. Normalization of every extracted field into proper typed values. Validation with VIN check digit algorithms, dollar amount sum checks, date plausibility, odometer consistency, and cross-field verification. An agentic correction loop using Gemini Flash that activates only when validation fails. Entity resolution that links documents to trucks, drivers, and vendors. Writing to both Postgres and Neo4j. Processing status updates emitted through Postgres NOTIFY. A human review queue for documents that fail validation and can't be auto-corrected.

After this phase, all 247 Sunflower Freight Lines PDFs are processed, the normalized tables are populated with real data, the Neo4j graph represents the complete fleet with all relationships, and you can verify every truck, driver, vendor, maintenance event, registration, insurance coverage, title, and IFTA filing in the database.

---

## The Extraction Worker Lifecycle

The extraction worker (built as a stub in Phase 1) now contains the full pipeline. It runs as a separate process, polls the Redis queue for jobs, and processes each document through all 7 layers.

When the worker picks up a job from the Redis queue, it receives the document_id and file_path. It loads the document record from Postgres, updates processing_status to "parsing," and emits a Postgres NOTIFY event on the "document_events" channel with payload: {document_id, status: "parsing", filename}. This pattern repeats at each major stage transition — the status updates flow through NOTIFY so the API server (and eventually the WebSocket layer in Phase 4) can track progress.

If any layer throws an unrecoverable error, the worker sets processing_status to "failed," stores the error details in the error_details column, and emits a NOTIFY event with the failure details. The document stays in the system for debugging — failed documents are never deleted.

If Layer 5 validation fails on specific fields and Layer 6 agentic correction cannot confidently fix them, the worker sets processing_status to "needs_review," populates the review_notes with the specific validation failures and attempted corrections, and emits a NOTIFY event. The document data is still written to the normalized tables with its best-effort extraction, but the parse_confidence is set below the review threshold (0.7) and a flag indicates which fields need human attention.

---

## Layer 1: Physical Reading

### Purpose
Determine the PDF's format and extract raw text with spatial coordinates.

### Input
File path to a PDF on disk.

### Process

Open the PDF with PyMuPDF (fitz). Attempt to extract text from every page using page.get_text(). If the total extracted text across all pages exceeds 100 characters of meaningful content (not just whitespace, headers, or page numbers), classify as text_pdf. If text extraction yields less than 100 meaningful characters, classify as image_pdf.

For text_pdf: extract full text from every page. Additionally extract text with position data using page.get_text("dict") which returns blocks with bbox coordinates. Store both the flat text (for full-text search and chunking) and the positioned text (for Layer 2 layout understanding). Record parse_method as "docling_fast."

For image_pdf: render each page to an image at 300 DPI using page.get_pixmap(dpi=300). These images are the input for Layer 3's Gemini Vision extraction. Record parse_method as "image_pdf." Also attempt OCR through Docling's hi-res strategy as a secondary text source.

### Output
A document reading result containing: source_format (text_pdf or image_pdf), page_count, full_text (concatenated text from all pages), positioned_blocks (list of text blocks with bounding box coordinates per page), page_images (list of PIL images, only for image PDFs).

### Status update
processing_status → "parsing" at start. No status change at completion — flows directly to Layer 2.

---

## Layer 2: Layout Understanding

### Purpose
Identify the structural elements of the document — sections, headers, key-value pairs, tables, footers — from the raw text and position data.

### Input
The document reading result from Layer 1.

### Process

For text_pdf documents, use Docling with fast strategy. Docling's DocLayNet model analyzes the positioned text blocks and classifies them into layout regions: title, section_header, key_value_pair, table, paragraph, footer, page_number. The output is a hierarchical document structure tree where each node is a classified region containing its text content and spatial coordinates.

For documents where Docling's fast strategy doesn't produce a clean structure (rare for machine-generated PDFs but possible), fall back to a heuristic-based layout parser: group text blocks into lines by vertical alignment, identify section headers by font size or uppercase patterns, detect key-value pairs by colon separators or spatial label-value alignment, detect tables by columnar alignment patterns.

For image_pdf documents, this layer is lighter — the structure understanding happens inside Layer 3's Gemini Vision call. But if Docling's hi-res strategy produced OCR text with positions, run the same layout analysis on that output.

### Output
A document structure object containing: document_title (if identified), sections (list of named sections, each containing key-value pairs, paragraphs, or tables), header_block (company name, address, identifiers from the top of the document), footer_block (document number, reference codes from the bottom).

---

## Layer 3: Field Extraction

### Purpose
Apply a document-type-specific extraction schema to the structure tree, mapping layout elements to typed fields.

### Process — Two sub-steps

**Sub-step 3a: Document Type Classification**

Before extracting fields, the system must know what type of document it's processing. Classification uses a priority-ordered approach:

Priority 1 — Document number prefix. If the document text contains a document number matching a known prefix pattern, that determines the type: BOS- → bill_of_sale, CDL- → cdl, GWCA- → insurance_card, CSS- or DEC- or FLP- or LTS- or PSC- or RPS- or RTR- or STM- or TSI- or VTW- or WBP- → service_invoice, KS-REG- → irp_cab_card, KS followed by a title-format number → title, IFTA- → ifta_filing.

Priority 2 — Header text keywords. Scan the first 500 characters for unambiguous keywords: "BILL OF SALE" → bill_of_sale, "COMMERCIAL DRIVER LICENSE" → cdl, "INSURANCE IDENTIFICATION CARD" → insurance_card, "INVOICE" → service_invoice, "APPORTIONED REGISTRATION" or "CAB CARD" → irp_cab_card, "CERTIFICATE OF TITLE" → title, "INTERNATIONAL FUEL TAX AGREEMENT" → ifta_filing.

Priority 3 — For Bill of Sale, sub-classify as purchase or sale: if the document header says "(Purchase)" → bill_of_sale_purchase. If "(Sale)" → bill_of_sale_sale. Alternatively, check if Sunflower Freight Lines is the BUYER (purchase) or the SELLER (sale).

Priority 4 — For image PDFs that have no extractable text yet, classification happens as part of the Gemini Vision extraction in the next sub-step.

If classification fails entirely, document_type is set to "unknown" and processing_status becomes "needs_review."

**Sub-step 3b: Schema-Guided Extraction**

Each document type has an extraction schema defining the target fields, where to find them in the structure tree, and what label variations to expect. The extraction approach differs between text PDFs and image PDFs.

---

### Text PDF Extraction — Rule-Based with Label Dictionaries

For text-layer PDFs, extraction is rule-based. Each document type has a schema containing: the target fields (name, type, required/optional), a label dictionary for each field (all known text variations of the field label), the section where the field is typically found, and any field-specific extraction patterns (regex, positional rules).

#### Bill of Sale (Purchase and Sale) — Extraction Schema

Target fields and their label dictionaries:

**fleet_unit_no** — Labels: "Fleet Unit No.", "Fleet Unit No", "Unit No." Extract from document header area. Also parseable from document number: BOS-2103-006 → unit 006 → 6.

**document_number** — Labels: "Document No.", "Document No", "Doc No." Extract from document header.

**document_date** — Labels: "Date of Sale", "Date of Sale:". Parse the full date string.

**vin** — Labels: "VIN", "V.I.N.", "Vehicle Identification Number". 17-character alphanumeric string in the vehicle description section.

**year** — Labels: "YEAR", "Model Year". Integer in the vehicle description section.

**make** — Labels: "MAKE", "Manufacturer". String in the vehicle description section.

**model** — Labels: "MODEL", "Model". String in the vehicle description section.

**body_type** — Labels: "BODY TYPE", "Body Type", "Type". String in the vehicle description section.

**color** — Labels: "COLOR", "Color". String in the vehicle description section.

**odometer** — Labels: "ODOMETER", "Odometer Reading". Number followed by "miles" in the vehicle description section.

**purchase_price** — Labels: "TOTAL PURCHASE PRICE", "Purchase Price", "Sale Price". Dollar amount in the price section.

**payment_method** — Labels: "METHOD OF PAYMENT", "Payment Method". String in the price section.

**seller_name** — Under the "SELLER" heading. First line is the company/person name.

**seller_address** — Under the "SELLER" heading. Second line is the address.

**buyer_name** — Under the "BUYER" heading. First line.

**buyer_address** — Under the "BUYER" heading. Second line.

**notary_name** — Under "NOTARY ACKNOWLEDGMENT." Pattern: "Notary Public, State of Kansas: [NAME]".

**notary_commission_expiry** — Pattern: "My commission expires: [DATE]".

For Bill of Sale (Sale), seller and buyer are swapped — Sunflower is the seller.

#### CDL — Extraction Schema

The CDL documents in the Sunflower dataset have a distinctive header line that contains critical metadata: "SCANNED DOCUMENT — CDL-D01 — D01 / FLEET 6". This header must be parsed first.

**driver_code** — From header: the "D01" portion. Pattern: CDL-D(\d+) or D(\d+).

**fleet_unit_assignment** — From header: the "FLEET 6" portion. Pattern: FLEET (\d+) or FLEET None. This links the driver to a truck.

**full_name** — The name appearing after "COMMERCIAL DRIVER LICENSE" / "CLASS" line. First full line of text that looks like a person name.

**last_name** — Labels: "1" (field number on CDL). Line starting with "1 ".

**first_name** — Labels: "2" (field number). Line starting with "2 ".

**address** — Labels: "8". Line starting with "8 ".

**date_of_birth** — Labels: "3 DOB", "DOB". Date value.

**license_issue_date** — Labels: "4a ISS", "ISS". Date value.

**license_expiry_date** — Labels: "4b EXP", "EXP". Date value.

**sex** — Labels: "15 SEX". Single character M or F.

**height** — Labels: "16 HGT". String like 6'-02".

**eye_color** — Labels: "18 EYES". 3-character code.

**weight** — Labels: "WGT". Number followed by "lb".

**license_class** — Labels: "9 CLASS". Single character or short code.

**license_number** — Labels: "4d DLN". Pattern: state prefix + number (K08-44-2917).

**endorsements** — Labels: "9a END". Comma-separated codes (T, N, H, X, P, S).

**restrictions** — Labels: "12 REST". Codes or "NONE".

#### Insurance Card — Extraction Schema

**policy_number** — Labels: "POLICY NUMBER", "Policy No.". String value.

**insurer_name** — The large company name block (GREAT WEST CASUALTY COMPANY).

**naic_number** — Labels: "NAIC CO. #", "NAIC". Number.

**agent_name** — Under or near "Agent" label. String value.

**coverage_type** — Labels: "COVERAGE / POLICY TYPE", "Coverage Type". String value.

**liability_limit** — Labels: "LIABILITY LIMIT". Dollar amount with description.

**cargo_limit** — Pattern: "Motor Truck Cargo Limit: $[AMOUNT]". Dollar amount.

**effective_date** — Labels: "EFFECTIVE DATE". Date value.

**expiry_date** — Labels: "EXPIRATION DATE". Date value.

**unit_number** — Pattern: "DESCRIBED VEHICLE · UNIT [NUMBER]" or "UNIT [NUMBER]". Integer.

**vehicle_description** — Line after unit number: "2018 Freightliner Cascadia 126". Parse into year, make, model if needed.

**license_plate** — Labels: "LICENSE PLATE". String value.

**vin** — Labels: "VEHICLE IDENTIFICATION NO. (VIN)", "VIN". 17-character string.

#### Service Invoice — Extraction Schema

The Sunflower invoices share a common template across all 11 vendors. The vendor changes but the field layout is consistent.

**vendor_name** — First line of the document (before the address). String.

**vendor_address** — Second line. Full address string.

**vendor_phone** — Line starting with "Tel". Phone number.

**invoice_number** — Labels: "INVOICE NO.", "Invoice No.", "Invoice #". String value. Note: the period in "INVOICE NO." may have special characters in PDF extraction — match with and without period.

**invoice_date** — Labels: "DATE" (in the invoice header area, not in the body). Date value.

**po_number** — Labels: "PO NO.", "PO #", "Purchase Order". String value.

**unit_number** — Labels: "UNIT #", "Unit #", "Unit No.". Integer. Located in the "UNIT / VEHICLE" section.

**category** — Labels: "CATEGORY". String value (Tires, Brakes, Engine, Suspension, Filters, Cooling, Lighting, Electrical, Air System, Emissions, Wheels, Warranty, Transmission, Fuel).

**vin** — Labels: "VIN". 17-character string in the vehicle section.

**line_items** — Table structure with columns: DESCRIPTION, QTY, UNIT PRICE, AMOUNT. Each row is a line item. Extract as a list of {description, quantity, unit_price, amount} objects.

**payment_status** — Labels: "STATUS". String value (PAID or UNPAID). Also detectable from the presence of "PAID" stamp text at the bottom of the document (the stamp appears as a large-font "PAID" followed by the date).

**payment_method** — Labels: "METHOD". String value (Fleet card ****, Company check, etc.).

**technician** — Labels: "TECHNICIAN". Person name.

**labor_cost** — Labels: "LABOR". Dollar amount.

**subtotal** — Labels: "SUBTOTAL". Dollar amount.

**sales_tax** — Labels: "SALES TAX". Dollar amount.

**total** — Labels: "TOTAL". Dollar amount. This is the grand total including labor.

**paid_stamp_date** — The date on the PAID stamp at the bottom. Pattern: large spaced-out text of the date (e.g., "J U LY 1 4 , 2 0 2 5"). Note the extreme letter-spacing in the PDF extraction.

#### IRP Cab Card — Extraction Schema

IRP cab cards are 2-page documents. Page 1 contains the registration receipt with fee breakdown. Page 2 contains the cab card with vehicle details and registration credentials. Both pages must be processed together.

**plate_number** — Labels: "LICENSE PLATE NO.", "License Plate". String.

**plate_state** — Labels: "PLATE STATE". String (Kansas).

**validation_decal** — Labels: "VALIDATION DECAL / STICKER NO.". String.

**vin** — Labels: "VEHICLE IDENTIFICATION NUMBER (VIN)", "VIN". 17-character string.

**year** — Labels: "YEAR". Integer.

**make** — Labels: "MAKE". String.

**model** — Labels: "MODEL". String.

**body_type** — Labels: "BODY / TYPE CODE". String (TKTR for Truck Tractor).

**registered_weight** — Labels: "REGISTERED GROSS WEIGHT (LBS)". Integer (typically 80,000).

**registration_class** — Labels: "REGISTRATION CLASS". String (Apportioned — IRP).

**unit_number** — Labels: "EQUIPMENT / UNIT NO.", "Unit No.". Integer.

**base_jurisdiction** — Labels: "BASE JURISDICTION". String (Kansas).

**irp_account_number** — Labels: "IRP ACCOUNT / FLEET NO.". String.

**registration_number** — Labels: "REGISTRATION RECEIPT NO.". String.

**effective_date** — Labels: "EFFECTIVE DATE". Date.

**expiry_date** — Labels: "EXPIRES", "EXPIRATION DATE". Date.

**registration_fee** — Labels: "Registration Fee (apportioned base)". Dollar amount.

**property_tax** — Labels: "Personal Property Tax", "PPT". Dollar amount.

**irp_apportioned_fee** — Labels: "IRP Apportioned Fee (member jurisdictions)". Dollar amount.

**title_fee** — Labels: "Title Fee". Dollar amount.

**total_fees** — Labels: "TOTAL FEES PAID". Dollar amount.

**issue_date** — Labels: "ISSUED". Date (when the cab card was issued, may differ from effective_date).

#### Kansas Vehicle Title — Extraction Schema

**title_number** — Labels: "TITLE NUMBER". String (KS18JL9921T format).

**title_state** — Labels: "TITLE STATE", "STATE OF". String.

**issue_date** — Labels: "DATE OF ISSUE". Date.

**vin** — Labels: "VEHICLE IDENTIFICATION NUMBER (VIN)". 17-character string.

**year** — Labels: "YEAR". Integer.

**make** — Labels: "MAKE". String.

**model** — Labels: "MODEL". String.

**color** — Labels: "COLOR". String.

**fuel_type** — Labels: "FUEL TYPE". String (Diesel).

**body_type** — Labels: "BODY TYPE / STYLE". String with code (Truck Tractor (TKTR)).

**gross_weight** — Labels: "GROSS VEHICLE WT. RATING (LBS)". Integer.

**odometer** — Labels: "ODOMETER READING (MILES)". Integer followed by mileage status.

**mileage_status** — Text after odometer: "ACTUAL MILEAGE", "EXEMPT", or "NOT ACTUAL".

**owner_name** — Labels: "OWNER NAME(S)". String.

**owner_address** — Labels: "MAILING ADDRESS". String.

**lien_holder** — Under "FIRST LIEN HOLDER" section. String or "NONE" / "NO LIEN OF RECORD ON THIS TITLE".

**previous_title_number** — Labels: "PREVIOUS TITLE NO.". String.

**previous_title_state** — Labels: "PREVIOUS TITLE STATE". String.

**control_number** — Labels: "CONTROL NUMBER". String.

**fleet_unit_no** — Labels: "FLEET UNIT NO.". Integer.

**title_fee** — Labels: "TITLE FEE". Dollar amount.

**certified_date** — Labels: "DATE CERTIFIED". Date at the bottom of the document.

#### IFTA Quarterly Filing — Extraction Schema

IFTA filings are 2-page documents. Page 1 has the header, jurisdiction table, and summary. Page 2 has per-vehicle details and the return summary.

**ifta_account** — Labels: "IFTA ACCOUNT NO.", "IFTA Licensee Account". String.

**carrier_name** — Under "LICENSEE / CARRIER". String.

**quarter** — From document identifier or header. Pattern: "2025 Q3" or extractable from the "QUARTER ENDING" field. Convert to format: 2025Q3.

**filing_date** — Labels: "DATE" (in the signature section). Date the return was signed/filed.

**jurisdiction_table** — Table on page 1 with columns per jurisdiction: jurisdiction name, total miles, taxable miles, taxable gallons, tax-paid gallons, net taxable gallons, tax rate, tax due or credit, surcharge. Extract as a list of jurisdiction detail objects.

**vehicle_table** — Table on page 2 with representative vehicles: fleet unit number (if present), VIN, miles, gallons. Extract as a list of vehicle detail objects.

**total_miles** — From the totals row of the jurisdiction table or from a summary field.

**total_gallons** — From totals.

**total_tax_due** — Labels: "Total tax / (credit) due — all jurisdictions". Dollar amount (may be negative for credits).

**penalty** — Labels: "Penalty (late filing / payment)". Dollar amount.

**interest** — Labels: "Interest". Dollar amount.

**balance_due** — Labels: "BALANCE DUE". Dollar amount (may be negative).

**average_fleet_mpg** — Labels: "Average Fleet Fuel Mileage". Decimal number followed by "MPG".

### Image PDF Extraction — Gemini Flash Vision

For the 5 image PDFs (documents 064-068), the rendered page images from Layer 1 are sent to Gemini Flash Vision with a document-type-specific extraction prompt.

Since the document type is unknown for image PDFs (no text to classify from), the Gemini call does classification and extraction in one pass. The prompt instructs: "This is a scanned fleet document. First, identify the document type (options: driver's license, insurance certificate, vehicle registration, inspection report, other). Then extract the structured fields for that document type."

The prompt includes the target schema for each possible document type so Gemini knows what fields to extract. The response is parsed as structured JSON.

If Gemini cannot classify the document or confidence is low, the document is flagged as "unknown" with processing_status "needs_review."

### Output
A raw extraction result containing: document_type (classified), extracted_fields (dict of field_name → raw string value), extraction_method (rule_based or gemini_vision), field_confidences (dict of field_name → confidence score 0.0-1.0), any extraction warnings or notes.

---

## Layer 4: Normalization

### Purpose
Convert raw extracted string values into properly typed values that can be stored in Postgres domain tables.

### Field Type Normalizations

**Integer fields** (unit_number, year, odometer, weight, registered_weight, gross_weight, page_count, miles, gallons): Strip commas. Strip unit suffixes ("miles", "lbs", "lb", "gallons"). Strip whitespace. Parse to integer. If parsing fails, flag the field.

**Decimal/money fields** (purchase_price, total_cost, labor_cost, sales_tax, all fee fields, tax amounts): Strip dollar signs. Strip commas. Strip text descriptions ("Fifty-one thousand and 00/100 dollars" — use the numeric version, not the written-out version). Parse to Decimal with 2 decimal places. If both numeric and written forms are present, prefer the numeric form. If they disagree, flag for validation.

**Date fields** (all dates): Handle multiple formats: "March 12, 2021", "03/12/2021", "2021-03-12", "04/22/2023". Use dateutil.parser with dayfirst=False (US date format). Output as ISO date (YYYY-MM-DD). If parsing fails, try common patterns in order. Dates that parse to before 1990 or after 2030 are flagged as implausible.

**VIN fields**: Uppercase. Strip all whitespace and hyphens. Verify length is exactly 17 characters. If length is not 17, flag the field. VINs should only contain characters 0-9 and A-Z excluding I, O, Q.

**Name fields** (driver names, vendor names, company names): Strip extra whitespace. Preserve original casing. For driver names, split into first_name and last_name if needed (from CDL, field 1 is last name, field 2 is first name).

**Address fields**: Preserve as-is, including line breaks and formatting. Only strip leading/trailing whitespace.

**Plate numbers**: Uppercase. Strip whitespace.

**Phone numbers**: Normalize to (XXX) XXX-XXXX format. Strip "Tel" prefix.

**License class, endorsements, restrictions**: Uppercase. Strip whitespace. Split endorsements on comma for multi-value fields.

**Height**: Preserve display format (6'-02"). Parse to inches as a secondary computed field if needed.

**Spaced-out text handling**: The PDF extraction frequently produces letter-spaced text like "T R U C K T I R E & S E RV I C E C E N T E R" or "P U R C HA S E PR I C E & PAY ME N T". The normalizer should collapse these by removing spaces between single characters while preserving normal word spacing. Detection rule: if a sequence has 3+ consecutive single-character-space-single-character patterns, collapse the spaces.

### Output
The same extracted_fields dict but with all values converted to proper types. A normalization_issues list recording any fields that couldn't be normalized (field_name, raw_value, error_description).

---

## Layer 5: Validation

### Purpose
Verify that extracted and normalized data is internally consistent and plausible. Each validation produces a pass/fail result per field with a confidence impact.

### VIN Validation

**Check digit validation**: Position 9 of a 17-character VIN is a check digit computed from the other 16 characters. The algorithm: each character has a transliteration value (A=1, B=2, ... H=8, J=1, K=2, ... N=5, P=7, R=9, S=2, ... Y=8, 0-9 = face value). Each position has a weight (8,7,6,5,4,3,2,10,0,9,8,7,6,5,4,3,2 for positions 1-17). Multiply each character's transliteration by its position weight, sum all products, divide by 11, remainder is the check digit (0-9, or X for remainder 10). Compare computed check digit against the actual character at position 9. If they match: VIN is valid. If not: VIN likely has a character error.

**VIN-make cross-reference**: The first three characters of the VIN (World Manufacturer Identifier) identify the manufacturer. Known WMI codes relevant to this dataset: 3AK or 3AL = Freightliner (Daimler), 4V4 = Volvo Trucks, 1XP or 1XK = Peterbilt, 3HS = Navistar (International). If the WMI doesn't match the extracted make, one of them is wrong.

**VIN-year cross-reference**: The 10th character of the VIN encodes the model year. A=2010, B=2011, C=2012, D=2013, E=2014, F=2015, G=2016, H=2017, J=2018, K=2019, L=2020, M=2021, N=2022, P=2023, R=2024, S=2025, T=2026. If the decoded year doesn't match the extracted year field, flag the discrepancy.

### Dollar Amount Validation

**Sum checks for invoices**: For service invoices, verify: (line item amounts should approximately sum to subtotal), (subtotal + labor + sales_tax should equal total). "Approximately" because rounding differences of up to $0.05 are acceptable. If the difference exceeds $1.00, flag the total as potentially misread.

**Written vs numeric amount**: For Bills of Sale, both "$62,000.00" and "Sixty-two thousand and 00/100 dollars" appear. If the numeric parse and the written parse disagree, flag both.

**Plausibility ranges**: Truck purchase prices should be between $5,000 and $500,000. Service invoice totals should be between $10 and $100,000. Registration fees should be between $50 and $20,000. Negative amounts are valid only in IFTA tax credits.

### Date Validation

**Temporal logic**: Purchase date cannot be before the model year of the truck (you can't buy a 2018 truck in 2015). Service dates should be after the truck's purchase date (you can't service a truck you don't own yet, though pre-purchase inspections are possible — flag but don't reject). Insurance effective dates should be before expiry dates. Registration effective dates should be before expiry dates. CDL issue dates should be before expiry dates. IFTA filing dates should be after the quarter end date.

**Recency check**: No document should have a date more than 1 year in the future from today. Documents with dates before 2015 are unusual for an active fleet and should be flagged.

### Odometer Validation

**Cross-document consistency**: For the same truck, odometer readings should monotonically increase over time. If a later document shows a lower odometer than an earlier document, one of them is wrong. Query existing mileage_records for the truck to check.

**Rate plausibility**: Commercial trucks typically drive 80,000-150,000 miles per year. If the implied annual mileage between two readings is below 20,000 or above 250,000, flag as unusual.

### Cross-Field Validation

**Entity consistency across documents**: When a service invoice references Unit #19 and VIN 3HSDZAPR7GN145782, verify that truck 19 in the trucks table has that VIN. If the VIN on the invoice doesn't match the registered VIN for that unit number, either the unit number or the VIN was misread.

**Duplicate detection**: Before creating a new maintenance_event, check if an event with the same invoice_number already exists. If so, this is a duplicate document (same invoice scanned twice). Flag it rather than creating a duplicate record.

**Vehicle description consistency**: When a document says "2018 Freightliner Cascadia 126" for Unit 6, verify this matches the trucks table. If the make or model differs, either this document or the original Bill of Sale has an error.

### Validation Output
A validation report containing: overall_valid (boolean), overall_confidence (0.0-1.0, reduced for each failed check), field_results (dict of field_name → {valid: boolean, check_type: string, expected: string, actual: string, confidence_impact: float}), needs_review (boolean, true if any critical field failed validation).

---

## Layer 6: Agentic Correction

### Purpose
Attempt to correct specific validation failures using LLM reasoning, activated ONLY when Layer 5 flags errors.

### When It Activates

Layer 6 runs only on fields that failed validation in Layer 5. It does NOT run on every document. It does NOT re-extract fields. It receives the specific validation failure context and attempts targeted correction.

### Correction Process Per Failed Field

**VIN check digit failure**: The corrector receives: the extracted VIN, the failed check digit computation (which position the error is likely in based on the algorithm), the raw text surrounding the VIN in the document, and common OCR confusion pairs (2↔Z, 5↔S, 0↔O, 1↔I/l, 8↔B, 6↔G). The LLM is prompted: "The VIN [extracted] fails the check digit at position 9. The raw text shows [context]. Common OCR errors are [list]. What is the correct VIN?" The proposed correction is then re-validated against the check digit algorithm. If it passes, the correction is accepted. If it fails, the field is flagged for human review.

**Dollar amount mismatch**: The corrector receives: the extracted subtotal, labor, tax, and total, plus which sum check failed. The LLM examines the raw text to determine which number was likely misread (e.g., $5,080 misread as $5,880 — the 0 and 8 are OCR-confusable). The proposed correction must satisfy the sum check.

**Date parsing failure**: The corrector receives: the raw date text that couldn't be parsed and the context. The LLM attempts to interpret ambiguous date formats (is "04/05/2023" April 5 or May 4? In US context, it's April 5).

**Cross-field inconsistency**: The corrector receives: the conflicting values from different fields or documents and the context. The LLM reasons about which value is more likely correct based on surrounding evidence.

### Correction Guardrails

Every correction proposed by the LLM must pass the same validation that originally failed. The LLM proposes, the algorithm validates. If the algorithm says the correction is wrong, the correction is rejected regardless of the LLM's confidence.

Corrections are logged in the extraction_corrections table with correction_source = "agentic_layer6". This enables tracking how often the agentic corrector succeeds and what types of errors it handles.

Maximum of 3 correction attempts per field. If all 3 fail, the field goes to human review.

### Output
A correction report: fields_attempted (list), fields_corrected (list with original and corrected values), fields_unresolvable (list — these go to human review).

### Status Update
If all validation failures were corrected: processing_status remains on track to "complete." If any fields remain unresolvable: processing_status → "needs_review" with the specific unresolvable fields noted.

---

## Layer 7: Semantic Enrichment — Write to Normalized Tables and Graph

### Purpose
Transform the validated extraction result into rows in Postgres normalized tables and nodes/relationships in Neo4j. This is where documents become fleet intelligence.

### Entity Resolution — Before Writing

Before writing to normalized tables, the system must resolve which existing entities (trucks, drivers, vendors) the document references, or create new ones.

**Truck resolution**: Extract the fleet_unit_no and/or VIN from the document. Query trucks table: first by VIN (exact match, highest confidence), then by unit_number (exact match, high confidence). If a match is found, use that truck_id. If no match and this is a Bill of Sale (the document that creates trucks), create a new truck record. If no match and this is not a Bill of Sale, flag for review — the document references a truck that doesn't exist in the system, which means either a Bill of Sale wasn't processed yet (ordering issue) or the unit number was misread.

**Driver resolution**: Extract driver_code and/or full_name from the document (CDLs have both). Query drivers table: first by license_number (exact match), then by driver_code, then by full_name (case-insensitive). If no match and this is a CDL, create a new driver record. If no match and this is not a CDL, flag for review.

**Vendor resolution**: Extract vendor_name and vendor_address. Query vendors table by name (case-insensitive, trimmed). If an exact match exists, use it. If no match, create a new vendor record. Vendor deduplication is by name+address — "Cummins Sales and Service" at "3500 N Toben St, Wichita, KS 67226" is one vendor entity regardless of how many invoices reference it.

**Processing order matters**: Bills of Sale should be processed before service invoices, insurance cards, IRP cards, and titles — because Bills of Sale create truck entities that other documents reference. CDLs should be processed before or alongside Bills of Sale — because CDLs create driver entities. The bulk import processor should sort documents by type in this order: Bills of Sale (Purchase) first, then CDLs, then everything else. Bills of Sale (Sale) should be processed after Purchase bills for the same truck.

### Postgres Writes Per Document Type

**Bill of Sale (Purchase):**
1. Create or update trucks record: unit_number, vin, year, make, model, body_type, color, status='active', acquired_date, purchase_price, initial_odometer.
2. Create or find vendors record for the seller.
3. Set trucks.acquired_from_vendor_id to the seller vendor.
4. Create mileage_records entry with the purchase odometer reading.
5. Create documents record.
6. Create document_normalized_records linking the document to the trucks record.

**Bill of Sale (Sale):**
1. Update existing trucks record: disposed_date, sale_price, disposed_to (buyer name), disposal_type='sold', status='sold'.
2. Create or find vendors record for the buyer (as vendor_type='buyer').
3. Create documents record.
4. Create document_normalized_records.
5. Close any active assignments for this truck (set end_date to the sale date).

**CDL:**
1. Create or update drivers record with all CDL fields.
2. If FLEET assignment is not "None": resolve the truck by unit_number. Create an assignments record linking the driver to the truck with start_date = CDL issue date (or a sensible default), assignment_type = 'primary', source_document_id = this CDL document. Check for existing active assignment for the same truck — if a different driver is currently assigned, close the old assignment (set end_date) before creating the new one.
3. Create documents record with driver_id set.
4. Create document_normalized_records.

**Insurance Card:**
1. Resolve the truck by unit_number and VIN.
2. Create or find vendors records for the insurer (vendor_type='insurance_company') and the agent (vendor_type='insurance_agent').
3. Create insurance_coverages record with all policy details.
4. Create documents record with truck_id set.
5. Create document_normalized_records.

**Service Invoice:**
1. Resolve the truck by unit_number and VIN.
2. Create or find vendors record for the service vendor.
3. Create maintenance_events record with all invoice details. Map the invoice's CATEGORY field to the maintenance_events.category. Combine line item descriptions into the description field. Map SUBTOTAL to parts_cost, LABOR to labor_cost, TOTAL to total_cost.
4. If the invoice contains an odometer reading, create a mileage_records entry.
5. Create documents record with truck_id and vendor_id set.
6. Create document_normalized_records.

**IRP Cab Card:**
1. Resolve the truck by unit_number and VIN.
2. Create registrations record with all registration details.
3. Create documents record with truck_id set.
4. Create document_normalized_records.

**Kansas Vehicle Title:**
1. Resolve the truck by fleet_unit_no and VIN.
2. Create titles record with all title details.
3. If odometer reading is present, create mileage_records entry.
4. Create documents record with truck_id set.
5. Create document_normalized_records.

**IFTA Quarterly Filing:**
1. Create ifta_filings record with filing-level summary data.
2. For each jurisdiction row in the jurisdiction table, create an ifta_jurisdiction_details record.
3. For each vehicle in the vehicle table, resolve the truck by VIN. Create an ifta_vehicle_details record with the resolved truck_id.
4. Create documents record (no single truck_id — IFTA is fleet-level).
5. Create document_normalized_records linking to the ifta_filings record.

### Neo4j Graph Writes Per Document Type

All Neo4j writes happen AFTER the Postgres writes succeed. Every Neo4j node stores a pg_id property containing the Postgres UUID for cross-referencing.

**Bill of Sale (Purchase):**
1. MERGE (:Truck {vin, unit_number, make, model, year, color, status, tenant_id, pg_id}).
2. MERGE (:Vendor {name, vendor_type, tenant_id, pg_id}) for the seller.
3. CREATE (Truck)-[:PURCHASED_FROM {date, price, odometer}]->(Vendor).
4. MERGE (:Document {document_type, document_number, document_date, pg_id}).
5. CREATE (Truck)-[:HAS_DOCUMENT]->(Document).

**Bill of Sale (Sale):**
1. MATCH the existing Truck node, update status to 'sold'.
2. MERGE (:Vendor) for the buyer.
3. CREATE (Truck)-[:SOLD_TO {date, price}]->(Vendor).
4. MERGE (:Document) and link.
5. Find the active (Driver)-[:ASSIGNED_TO {end_date: null}]->(Truck) relationship and set end_date.

**CDL:**
1. MERGE (:Driver {driver_code, full_name, license_number, license_class, license_expiry, status, tenant_id, pg_id}).
2. If fleet assignment exists: MATCH the Truck node by unit_number. CREATE (Driver)-[:ASSIGNED_TO {start_date, end_date: null, assignment_type: 'primary'}]->(Truck). If a different driver has an active ASSIGNED_TO relationship to this truck, set its end_date.
3. MERGE (:Document) and CREATE (Driver)-[:HAS_DOCUMENT]->(Document).

**Insurance Card:**
1. MATCH the Truck node.
2. MERGE (:InsurancePolicy {policy_number, insurer_name, effective_date, expiry_date, liability_limit, tenant_id, pg_id}).
3. CREATE (Truck)-[:COVERED_BY {effective_date, expiry_date, coverage_type}]->(InsurancePolicy).
4. MERGE (:Vendor) for insurer and agent. CREATE (InsurancePolicy)-[:ISSUED_BY]->(Vendor insurer). CREATE (InsurancePolicy)-[:BROKERED_BY]->(Vendor agent).
5. MERGE (:Document) and link.

**Service Invoice:**
1. MATCH the Truck node.
2. MERGE (:Vendor) for the service vendor.
3. CREATE (Truck)-[:MAINTAINED_AT {service_date, category, total_cost, invoice_number}]->(Vendor).
4. MERGE (:Document) and CREATE (Truck)-[:HAS_DOCUMENT]->(Document) and (Vendor)-[:HAS_DOCUMENT]->(Document).

**IRP Cab Card:**
1. MATCH the Truck node.
2. CREATE (Truck)-[:REGISTERED_IN {effective_date, expiry_date, plate_number, registration_number, state: 'Kansas'}]->(state).
3. MERGE (:Document) and link.

**Kansas Vehicle Title:**
1. MATCH the Truck node.
2. CREATE (Truck)-[:TITLED_IN {title_number, issue_date, state: 'Kansas'}]->(state).
3. MERGE (:Document) and link.

**IFTA Filing:**
1. MERGE (:IFTAFiling {quarter, filing_date, total_miles, total_gallons, average_mpg, tenant_id, pg_id}).
2. For each vehicle detail: MATCH the Truck node by VIN. CREATE (Truck)-[:REPORTED_IN {miles, gallons}]->(IFTAFiling).
3. MERGE (:Document) and link.

### Document Chunking and Embedding

After writing to normalized tables and graph, the raw_extracted_text is chunked for semantic search:

Split the full text into chunks of approximately 500 characters with 100-character overlap, splitting on paragraph or section boundaries where possible. For structured documents (Bills of Sale, IRP cards), chunk by section rather than by character count — each named section becomes a chunk.

Each chunk is embedded using a text embedding model (text-embedding-3-small from OpenAI, or Gemini's embedding model, or a local model like all-MiniLM-L6-v2 — the choice depends on cost/quality tradeoff; for MVP, a local model avoids API costs).

Chunks are stored in document_chunks with denormalized metadata (truck_id, driver_id, document_type, document_date) for filtered vector search.

### Completion Event

After all writes succeed (Postgres + Neo4j + chunks), the worker emits a Postgres NOTIFY on the "document_events" channel with payload: {document_id, status: "complete", document_type, truck_id (if applicable), driver_id (if applicable), vendor_id (if applicable), affected_tables: [list of tables that received new rows]}.

The document record is updated: processing_status → "complete", parse_confidence → computed from validation results.

---

## Bulk Import Processing

For the initial ingestion of all 247 Sunflower PDFs, the system needs to handle ordering and parallelism correctly.

**Ordering**: Documents are sorted into processing waves:
- Wave 1: Bills of Sale (Purchase) — creates truck entities. Process all 19 first.
- Wave 2: CDLs — creates driver entities and assignments. Process all 20 second.
- Wave 3: Bills of Sale (Sale) — updates truck status. Process all 4 third.
- Wave 4: Everything else (insurance, invoices, IRP, titles, IFTA, image PDFs) — references existing entities. Process in parallel.

**Parallelism within a wave**: Within Wave 4, documents can be processed in parallel (5-10 concurrent workers) since they reference different trucks. The entity resolution step handles the rare case of two documents referencing the same truck simultaneously through database-level locking (SELECT FOR UPDATE on the trucks row being updated).

**Progress tracking**: During bulk import, each document completion event updates a progress counter. The total is known (247 documents). Progress can be reported as: "Processing wave 2 of 4 (CDLs)... 15 of 20 complete" and then "Processing wave 4 (invoices, insurance, etc.)... 142 of 204 complete."

---

## Human Review Queue

Documents that reach processing_status = "needs_review" are surfaced in a review interface (built in Phase 4, but the data structures exist in Phase 2).

The review queue query: SELECT from documents WHERE processing_status = 'needs_review' ORDER BY created_at DESC.

Each reviewable document has: the original PDF file path (for viewing), the extracted fields with their confidence scores (highlighting low-confidence fields), the validation failure details (what failed and why), any agentic correction attempts and their results, and the partially-written normalized data (best-effort extraction already in the domain tables, flagged as low-confidence).

The review API endpoints (for Phase 4):
- GET /api/documents/review — list documents needing review
- GET /api/documents/{id}/review — get review details for a specific document
- POST /api/documents/{id}/review — submit corrections: updated field values, approval status

When a correction is submitted: the extraction_corrections table gets a new record, the normalized table row is updated with the corrected value, the document's processing_status changes to "complete" and review_status changes to "corrected", the Neo4j graph is updated if the correction affects a graph property.

---

## Phase 2 Acceptance Criteria

1. All 247 Sunflower PDFs are processed through the full pipeline.

2. The trucks table contains exactly 23 rows — 16 with status 'active', 4 with status 'sold' (units 47, 55, 63, 70), and 3 with appropriate status based on their document coverage.

3. The drivers table contains exactly 20 rows with all CDL details correctly extracted (name, license number, class, endorsements, restrictions, expiry dates).

4. The assignments table contains at least 16 rows linking the 16 assigned drivers to their trucks (D01→Unit 6, D02→Unit 12, D03→Unit 19, D04→Unit 37, D05→Unit 51, D06→Unit 62, D07→Unit 84, D08→Unit 9, D09→Unit 14, D10→Unit 21, D11→Unit 28, D12→Unit 33, D13→Unit 44, D14→Unit 58, D15→Unit 77, D16→Unit 88). The 4 unassigned drivers (D17-D20) have no active assignments.

5. The maintenance_events table contains exactly 77 rows (one per service invoice) with correct truck_id, vendor_id, category, costs, and invoice numbers.

6. The vendors table contains all 11 service vendors plus equipment sellers from Bills of Sale plus the insurance company and agent — each appearing exactly once (no duplicates).

7. The insurance_coverages table contains 20 rows (one per insurance card) linking to the correct trucks with policy number GWCA-KS-77 04188 and correct effective/expiry dates.

8. The registrations table contains 16 rows (one per IRP cab card) with correct plate numbers, VINs, effective/expiry dates, and fee breakdowns.

9. The titles table contains 19 rows with correct title numbers, issue dates, and VINs.

10. The ifta_filings table contains 3 rows (2025Q3, 2025Q4, 2026Q1) with correct summary data. The ifta_jurisdiction_details table contains the per-jurisdiction breakdowns. The ifta_vehicle_details table contains per-vehicle records linked to the correct truck_ids.

11. Every VIN in the trucks table passes the check digit validation algorithm.

12. Every VIN cross-references correctly — the WMI matches the make and the model year character matches the year.

13. Neo4j contains: 23 Truck nodes, 20 Driver nodes, all Vendor nodes, InsurancePolicy nodes, IFTAFiling nodes, and Document nodes. Relationships correctly connect drivers to trucks (ASSIGNED_TO), trucks to vendors (PURCHASED_FROM, MAINTAINED_AT), trucks to policies (COVERED_BY), etc.

14. The 4 sold trucks have SOLD_TO relationships in Neo4j and their ASSIGNED_TO relationships (if any) have end_dates set.

15. The documents table contains 247 rows. At least 237 have processing_status = 'complete' (allowing for up to 10 that might need review due to extraction challenges on image PDFs or unusual formatting). Any documents with status 'needs_review' have clear review_notes explaining what failed.

16. Postgres NOTIFY events were emitted for every document completion. The event payloads contain the correct document_id, document_type, entity references, and affected table lists.

17. The document_normalized_records junction table correctly links every document to every normalized record it produced — enabling full traceability from any data point back to its source document.

18. The mileage_records table contains odometer entries from Bills of Sale (initial odometer at purchase), titles (odometer reading), and any service invoices that included odometer data.

19. No duplicate records exist in any normalized table. The same invoice processed twice does not create two maintenance_events rows.

20. The extraction_corrections table contains records for any agentic corrections that were applied in Layer 6, with original and corrected values logged.

---

## Dependencies for Phase 3

Phase 3 (Sub-agents + API Layer) requires all normalized tables to be populated with real data from the 247 documents. The sub-agent functions query these tables for aggregations, comparisons, and lookups. Phase 3 also requires Neo4j to be populated so that graph traversal sub-agents can query relationships. The document_chunks table with embeddings must be populated for semantic search sub-agents.

---

## What Phase 2 Does NOT Build

- No API endpoints for querying the extracted data (Phase 3)
- No dashboard UI (Phase 4)
- No WebSocket push of extraction events to frontend (Phase 4 — the NOTIFY events are emitted but nothing listens on the frontend side yet)
- No chat functionality (Phase 5)
- No anomaly detection or fleet intelligence (Phase 6)
- No review queue UI (Phase 4 — the data structures and flagging exist but the review interface doesn't)
