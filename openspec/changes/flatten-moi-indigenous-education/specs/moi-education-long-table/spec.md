## ADDED Requirements

### Requirement: Emit a district-level education-attainment long table

The system SHALL emit one long table covering every retrieved statistical year at district granularity.

Each row SHALL carry the columns `統計年`, `縣市`, `鄉鎮市區`, `身分別`, `教育程度`, `性別`, and `人數`. Every column SHALL be non-empty on every row.

#### Scenario: The long table covers the published years

- **WHEN** the long table is built
- **THEN** the set of `統計年` values is 106 through 114
- **AND** `人數` holds non-negative integers throughout

#### Scenario: Status values follow the year

- **WHEN** the year 114 is read
- **THEN** three status values are present
- **AND** for every year before 114 only two are present

##### Example: measured row counts per year

| Year | Source rows | Statuses | Rows per village | Villages implied |
| ---- | ----------: | -------: | ---------------: | ---------------: |
| 106 | 722,292 | 2 | 92 | 7,851 |
| 110 | 711,528 | 2 | 92 | 7,734 |
| 112 | 712,816 | 2 | 92 | 7,748 |
| 113 | 712,815 | 2 | 92 | 7,747 plus a remainder of 91 |
| 114 | 1,069,776 | 3 | 138 | 7,752 |

### Requirement: Normalize education levels to their full spellings

The source writes the 23 education levels two different ways: abbreviated in years 106 and 107, spelled out from 108 onward. Carrying both would split every education series in two at the 107/108 boundary.

The system SHALL record the spelled-out form as canonical, and the registry SHALL map each abbreviation to it. An education value the registry does not describe SHALL be a blocking error.

#### Scenario: Both spellings converge

- **WHEN** years from either side of the 107/108 boundary are built
- **THEN** the set of `教育程度` values is identical across all years
- **AND** no value is an abbreviation

##### Example: abbreviations whose literal reading differs from their coverage

| Abbreviation | Canonical value | Why the literal reading misleads |
| ------------ | --------------- | -------------------------------- |
| `二畢` | 二、三專畢業 | reads as two-year college only, but covers both two- and three-year |
| `後二畢` | 五專畢業 | reads as "graduated the latter two years", but denotes graduating the five-year programme |
| `前三肄` | 五專前三年肄業 | the programme is only identifiable from the canonical form |

#### Scenario: An unmapped education value appears

- **WHEN** a year holds an education value absent from the registry
- **THEN** the system reports the year and the value
- **AND** no output is written for that year

### Requirement: Resolve the status column across its naming variants

The column carrying indigenous status is named three different ways across the nine years, and one year names every column in Chinese.

The system SHALL resolve the status column by consulting the registry rather than assuming a single name, and SHALL treat an unresolvable column set as a blocking error.

#### Scenario: Each variant resolves

- **WHEN** a year is read
- **THEN** the status column is located whether it is named in romanised or Chinese form

##### Example: the variants measured across the nine years

| Years | Status column | Column names |
| ----- | ------------- | ------------ |
| 106–112 | `aborigine` | romanised |
| 113 | `原住民身分` | Chinese |
| 114 | `indigenous` | romanised |

#### Scenario: A byte-order mark precedes the first key

- **WHEN** a year's first JSON key carries a byte-order mark
- **THEN** the key is matched as though the mark were absent

##### Example: years whose first key carries the mark

| Year | First key as returned |
| ---- | --------------------- |
| 106 | mark followed by `statistic_yyy` |
| 108 | mark followed by `statistic_yyy` |

#### Scenario: The column set cannot be resolved

- **WHEN** no registry variant matches a year's columns
- **THEN** the system reports the year and the actual column names
- **AND** no output is written for that year

### Requirement: A missing dimension combination is reported, not filled

Year 113 returns one row fewer than the complete dimension cross product. Filling the gap with zero would assert a figure the source never published; discarding the year would lose roughly 712,000 rows over one.

The system SHALL report which dimension combination is absent, SHALL record it in the retrieval record, and SHALL emit the year without that combination.

#### Scenario: A year is short of the cross product

- **WHEN** a year's row count is not a whole multiple of its rows-per-village
- **THEN** the system reports the absent dimension combination
- **AND** the retrieval record names that combination
- **AND** the year is still emitted, without a row for it

#### Scenario: No row is invented

- **WHEN** the long table is built
- **THEN** no row exists for a combination the source did not publish

### Requirement: Builds are reproducible and offline

The long table SHALL be a deterministic function of the persisted retrieval results, and building SHALL NOT perform any network request. The gzip header timestamp SHALL be fixed so that compression does not make output differ between runs.

#### Scenario: Two consecutive builds agree

- **WHEN** the long table is built twice from unchanged inputs
- **THEN** both runs produce byte-identical output

#### Scenario: Invariant tests detect a seeded fault

- **WHEN** a fault is injected into the cross-product completeness check or into the education-level normalisation
- **THEN** the corresponding test fails
