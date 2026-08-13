## ADDED Requirements

### Requirement: Retrieve source workbooks for a range of academic years

The system SHALL retrieve the Ministry of Education indigenous student statistics workbook for each academic year in a caller-specified range, storing each file under the raw data directory.

The file extension differs across years: academic years 103 through 108 are published as `.xls`, and 109 onward as `.xlsx`. The system SHALL NOT assume a single extension, and SHALL attempt the extension appropriate to the year first.

#### Scenario: Retrieving the full supported range

- **WHEN** the caller requests academic years 103 through 114
- **THEN** the system stores 12 workbook files in the raw data directory
- **AND** years 103 through 108 are stored as `.xls` files
- **AND** years 109 through 114 are stored as `.xlsx` files

##### Example: extension boundary

| Academic year | Extension retrieved | Notes |
| ------------- | ------------------- | ----- |
| 107 | `.xls` | legacy format |
| 108 | `.xls` | last legacy year; the `.xlsx` URL returns HTTP 404 |
| 109 | `.xlsx` | first modern year |
| 114 | `.xlsx` | current year |

#### Scenario: A year is unavailable in every known extension

- **WHEN** retrieval of a given academic year fails for every attempted extension
- **THEN** the system reports the academic year and every URL it attempted
- **AND** the system MUST NOT silently skip that year

### Requirement: Retrieval is idempotent and reproducible

Raw files are excluded from version control, so retrieval SHALL be repeatable and SHALL produce the same local state on every run.

#### Scenario: Re-running retrieval when files already exist

- **WHEN** retrieval runs a second time and a complete file for a year is already present
- **THEN** the system does not download that year again
- **AND** the resulting local file is unchanged

#### Scenario: Building without network access

- **WHEN** the raw data directory already contains every required workbook
- **THEN** downstream extraction and long-table construction complete without performing any network request
