# moe-table-extraction Specification

## Purpose

TBD - created by archiving change 'flatten-moe-indigenous-c-series'. Update Purpose after archive.

## Requirements

### Requirement: Locate worksheets by normalized table code

Worksheet names carry incidental whitespace, and worksheet titles are not a reliable identifier: the dash character in titles differs both across years and across tables within a single workbook.

The system SHALL locate a worksheet by comparing its name to the requested table code after trimming surrounding whitespace. The system SHALL NOT identify a worksheet by matching its title text.

#### Scenario: Worksheet name carries trailing whitespace

- **WHEN** the workbook for academic year 113 is searched for table code `A1-1`
- **AND** the workbook contains a worksheet literally named `A1-1 `
- **THEN** the system resolves that worksheet as table `A1-1`

#### Scenario: Requested table code is absent

- **WHEN** a requested table code matches no worksheet after normalization
- **THEN** the system reports the academic year, the requested table code, and the list of worksheet names actually present in that workbook

##### Example: title dash characters that MUST NOT be used for matching

| Academic year | Table | Dash character in title | Notes |
| ------------- | ----- | ----------------------- | ----- |
| 108 | `C2-1` | U+2014 em dash | legacy convention |
| 114 | `C2-1` | fullwidth hyphen | modern convention |
| 114 | `C2-4` | U+2014 em dash | same workbook as the row above, different dash |


<!-- @trace
source: flatten-moe-indigenous-c-series
updated: 2026-08-13
code:
  - .gitattributes
  - scripts/moe/__init__.py
  - scripts/moe/known_issues.py
  - docs/來源盤點.md
  - scripts/catalog/fetch_odportal_resources.py
  - scripts/moe/extract.py
  - catalog/odportal-763-graded.csv
  - data/processed/moe-c-series-long.csv
  - scripts/catalog/probe_resources.py
  - scripts/moe/registry.py
  - scripts/moe/build_long_table.py
  - catalog/品質分級報告.md
  - docs/schema/moe-c-series.md
  - README.md
  - scripts/moe/fetch.py
  - scripts/catalog/grade.py
tests:
  - tests/test_moe_long_table.py
-->

---
### Requirement: Identify data columns by header text and data presence together

Workbooks from academic year 109 onward carry a watermark column holding the academic year label. This column is not a data column, and it can contain stray values, so presence of a value in the data region is not sufficient to identify a data column.

The system SHALL treat a column as a data column only when that column both carries header text in the header rows and holds values in the data region.

#### Scenario: Watermark column carrying a stray value

- **WHEN** table `C2-2` of academic year 111 is extracted
- **AND** its final column contains only the label `111學年` and one stray `0`
- **THEN** the system excludes that column from the extracted data columns

#### Scenario: An unregistered data column appears

- **WHEN** extraction finds a column satisfying both conditions that the table registry does not describe
- **THEN** the system reports an error identifying the academic year, table code, and column header
- **AND** the system MUST NOT include the column in the output


<!-- @trace
source: flatten-moe-indigenous-c-series
updated: 2026-08-13
code:
  - .gitattributes
  - scripts/moe/__init__.py
  - scripts/moe/known_issues.py
  - docs/來源盤點.md
  - scripts/catalog/fetch_odportal_resources.py
  - scripts/moe/extract.py
  - catalog/odportal-763-graded.csv
  - data/processed/moe-c-series-long.csv
  - scripts/catalog/probe_resources.py
  - scripts/moe/registry.py
  - scripts/moe/build_long_table.py
  - catalog/品質分級報告.md
  - docs/schema/moe-c-series.md
  - README.md
  - scripts/moe/fetch.py
  - scripts/catalog/grade.py
tests:
  - tests/test_moe_long_table.py
-->

---
### Requirement: Restore dimension labels spanning merged rows

Some tables place a group's dimension label on the middle row of the group rather than the first row, because the source cell is merged and vertically centred. Forward-fill and backward-fill are each incorrect for this layout.

The system SHALL determine group boundaries first, then apply the single non-empty label found within a group to every row of that group.

#### Scenario: Ethnic group label centred on a three-row group

- **WHEN** table `C1-1` is extracted
- **AND** a group consists of three consecutive rows labelled 計, 男, 女
- **AND** the ethnic group name appears only on the second of those three rows
- **THEN** all three extracted rows carry that ethnic group name

##### Example: label placement in academic year 114 table C1-1

- **GIVEN** rows 8, 9, 10 hold 計, 男, 女 and the label `阿美族` appears only on row 9
- **WHEN** the group is extracted
- **THEN** rows 8, 9, and 10 each carry ethnic group `阿美族`


<!-- @trace
source: flatten-moe-indigenous-c-series
updated: 2026-08-13
code:
  - .gitattributes
  - scripts/moe/__init__.py
  - scripts/moe/known_issues.py
  - docs/來源盤點.md
  - scripts/catalog/fetch_odportal_resources.py
  - scripts/moe/extract.py
  - catalog/odportal-763-graded.csv
  - data/processed/moe-c-series-long.csv
  - scripts/catalog/probe_resources.py
  - scripts/moe/registry.py
  - scripts/moe/build_long_table.py
  - catalog/品質分級報告.md
  - docs/schema/moe-c-series.md
  - README.md
  - scripts/moe/fetch.py
  - scripts/catalog/grade.py
tests:
  - tests/test_moe_long_table.py
-->

---
### Requirement: Table structure is described as registry data

The six C-series tables differ in data column offsets and in which dimensions they carry. Encoding each layout as bespoke parsing logic does not scale to the full set of table codes.

The system SHALL describe each table's data start row, dimension columns, and measure columns as registry data, and the extraction logic SHALL operate by reading that registry. Adding a table SHALL require adding a registry entry, not new parsing logic.

The registry SHALL also carry the two facts that cannot be read off the sheet: which `等級別` × `年級` combinations are legal for the table, and how a level-relative grade label maps to an absolute school-system grade.

#### Scenario: Registry declares legal dimension combinations

- **WHEN** a registry entry describes a table carrying both level and grade dimensions
- **THEN** the entry declares the legal grade range for each level
- **AND** extraction consults that declaration rather than inferring legality from cell contents

#### Scenario: Registry describes column semantics by header text

- **WHEN** a registry entry describes a measure column
- **THEN** the entry identifies that column by its expected header text
- **AND** extraction verifies the actual header text matches before reading values

#### Scenario: Layout shifts horizontally between years

- **WHEN** a table's data columns shift position between two academic years while their header texts are unchanged
- **THEN** extraction resolves the columns by header text and produces equivalent output for both years

<!-- @trace
source: flatten-moe-indigenous-c-series
updated: 2026-08-13
code:
  - .gitattributes
  - scripts/moe/__init__.py
  - scripts/moe/known_issues.py
  - docs/來源盤點.md
  - scripts/catalog/fetch_odportal_resources.py
  - scripts/moe/extract.py
  - catalog/odportal-763-graded.csv
  - data/processed/moe-c-series-long.csv
  - scripts/catalog/probe_resources.py
  - scripts/moe/registry.py
  - scripts/moe/build_long_table.py
  - catalog/品質分級報告.md
  - docs/schema/moe-c-series.md
  - README.md
  - scripts/moe/fetch.py
  - scripts/catalog/grade.py
tests:
  - tests/test_moe_long_table.py
-->