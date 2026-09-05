# Specification workflow

1. Confirm the Excel workbook contains one API list plus one sheet per TR.
2. Confirm JSON top-level keys match the API IDs and preserve UTF-8 Korean text.
3. Rebuild the catalog with the bundled wrapper.
4. Check totals and review every `blocked-mutation` classification.
5. Spot-check `usa06011`, `usa20100`, `usa20280`, `ust21110`, `ust21070`, and all blocked TRs against Excel.
6. Never copy request or response examples containing realistic tokens or account numbers into fixtures.
7. Add implementation coverage only from runtime source files; exclude tests and documentation.

The current JSON omits Excel's Required column. Do not infer required fields solely from empty examples. Preserve request fields and validate requiredness in hand-written request builders using the Excel source.
