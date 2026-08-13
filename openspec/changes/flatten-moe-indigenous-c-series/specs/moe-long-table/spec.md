## ADDED Requirements

### Requirement: Emit a single long table with a mandatory table code column

The system SHALL emit one long table covering all six C-series table codes across academic years 103 through 114.

Each row SHALL carry the columns `學年`, `表號`, `統計別`, `等級別`, `年級`, `族籍別`, `性別`, `設立別`, `學校所在地`, `校碼`, `學校名稱`, and `人數`. Dimension columns not applicable to a given row SHALL be empty. The columns `學年`, `表號`, `統計別`, and `人數` SHALL never be empty.

Which dimension columns are non-empty is determined by table code **and** statistic type together, not by table code alone: in `C2-1` and `C2-2` the enrolled-student measures are broken down by grade while the graduate measure is a single undifferentiated total, so graduate rows in those tables carry an empty `年級`.

`表號` is mandatory because the six tables slice the same student population along different dimensions. Aggregating across table codes multiplies the population, and this column is the structural basis for preventing that misuse.

`校碼` is required because school names alone do not identify a school: academic year 114 table `C2-2` lists 2,298 schools under only 1,921 distinct names, and `C2-1` and `C2-2` carry no county column with which to disambiguate them.

#### Scenario: School codes retain their source form

- **WHEN** a row originates from `C2-1` or `C2-2`
- **THEN** `校碼` is non-empty and holds a string
- **AND** codes with leading zeros or an embedded `E` retain their exact source form

##### Example: school codes that a numeric read would corrupt

| Source cell | Correct value | Value if read as a number |
| ----------- | ------------- | ------------------------- |
| `011301` | `011301` | `11301.0` — leading zero lost |
| `173E16` | `173E16` | `1.73e+18` — parsed as scientific notation |

#### Scenario: Duplicate school names remain distinguishable

- **WHEN** the long table is filtered to one academic year and table code `C2-2`
- **THEN** rows sharing a `學校名稱` are distinguished by their `校碼`

##### Example: repeated school names in academic year 114

| `學校名稱` | Number of distinct schools |
| ---------- | -------------------------- |
| `縣立中正國小` | 9 |
| `市立信義國小` | 7 |
| `縣立中興國小` | 7 |

#### Scenario: Long table covers the declared scope

- **WHEN** the long table is built
- **THEN** the set of distinct `學年` values is exactly 103 through 114
- **AND** the set of distinct `表號` values is exactly the six C-series table codes
- **AND** no row has an empty `人數`

#### Scenario: Values conform to declared types

- **WHEN** the long table is read
- **THEN** `學年` holds integers denoting the ROC academic year
- **AND** `人數` holds non-negative integers
- **AND** `統計別` holds either the enrolled-student value or the prior-year-graduate value

### Requirement: Exclude aggregate rows and aggregate columns

Aggregate values in the source are exactly derivable from their detail values, and including them would cause any unfiltered aggregation to overcount by a factor of two or more.

The system SHALL emit only the finest-grained detail rows and detail columns. Aggregate values SHALL be used to verify the extraction and SHALL then be discarded.

#### Scenario: No aggregate rows survive into the long table

- **WHEN** the long table is built
- **THEN** no row represents a total across a dimension
- **AND** no row represents a combined-sex total where the sex breakdown is available

#### Scenario: Aggregate verification fails

- **WHEN** an aggregate value does not equal the sum of its detail values for some academic year and table code
- **THEN** the system reports the academic year, table code, location, and the difference
- **AND** the build stops without emitting a long table

##### Example: verified aggregate identities in academic year 114

| Table | Identity checked | Observed result |
| ----- | ---------------- | --------------- |
| `C1-1` | total column equals sum of the four level columns | holds for all 54 rows, enrolled and graduate |
| `C1-1` | 計 row equals 男 row plus 女 row | holds for all 180 cells |
| `C1-1` | total group equals sum of the 17 ethnic groups | enrolled 76,594 and graduate 15,062 match exactly |
| `C2-1` | total column equals sum of the three grade columns | holds for all 931 rows |

### Requirement: Dash cells are read as zero

The dash `-` is the only non-alphanumeric marker present anywhere in the C-series across academic years 103 through 114, occurring in 269 cells. It denotes an absent count rather than a suppressed one: treating it as zero leaves every aggregate identity exact, whereas suppression of a non-zero count would make the detail sum fall short of its total.

The system SHALL read a measure cell holding `-` as the integer 0. This SHALL apply only to `-`; no other marker is granted this treatment. This treatment applies only to cells inside a legal dimension combination — see the requirement on impossible combinations below.

#### Scenario: Dash cells resolve to zero without breaking aggregates

- **WHEN** a measure cell holds `-`
- **THEN** it is read as the integer 0
- **AND** the aggregate identities for that row still hold exactly

##### Example: dash resolved by aggregate identity in academic year 114

| Table | Row | Identity checked | Implied value of `-` |
| ----- | --- | ---------------- | -------------------- |
| `C1-2` | 新北市 graduates | `1680 = 741 + 938 + '-' + 1` | 0 |
| `C1-2` | 臺北市 graduates | `2696 = 936 + 1759 + 1 + '-'` | 0 |

### Requirement: Values that cannot be read as counts are surfaced as errors

Apart from `-`, silently coercing or dropping unreadable cells would hide a suppression convention introduced by a future revision and corrupt the output.

The system SHALL treat any cell in a measure column that is neither `-` nor readable as a non-negative integer as a blocking error, and SHALL report the raw cell content.

#### Scenario: A measure cell holds a non-numeric marker

- **WHEN** a measure cell holds a value that is neither `-` nor a non-negative integer
- **THEN** the system reports the academic year, table code, position, and the raw cell content
- **AND** the build stops

### Requirement: Impossible dimension combinations produce no rows

The dash carries two distinct meanings in the source. Where the combination of dimensions can exist, a dash means a count of zero. Where the combination cannot exist, a dash means the cell is inapplicable — a junior high school has no fourth grade.

Emitting the inapplicable case as a zero would state something false, and the distinction would not be recoverable from the long table. A user filtering to a non-existent combination SHALL receive no rows rather than a row holding zero.

The system SHALL emit a row only when the row's dimension combination is declared legal for that table code, and SHALL derive legality from the registry rather than from the presence of a dash.

#### Scenario: A grade outside the level's range

- **WHEN** table `C2-3` of academic year 114 is extracted
- **AND** the cell at the junior-high level and the fourth-grade column holds `-`
- **THEN** no row is emitted for that combination

#### Scenario: A zero inside a legal combination

- **WHEN** a cell holds `-` and its dimension combination is legal
- **THEN** a row is emitted with `人數` equal to 0

##### Example: the two meanings of a dash in academic year 114 table C2-3

| Row | Combination | Dash means | Emitted |
| --- | ----------- | ---------- | ------- |
| r10 | 國中 × 四年級 | inapplicable — level has no fourth grade | no row |
| r21 | 國中進修部 × 國立 | zero students | row with `人數` = 0 |

### Requirement: Grades are expressed as absolute school-system grades

The same grade dimension is labelled differently across tables: `C2-1` labels junior high grades `七年級` through `九年級`, while `C2-3` and `C2-4` label the same students `一年級` through `三年級`, meaning the n-th grade within that level. Carrying both conventions in one column would make a filter on `七年級` silently miss the `C2-3` and `C2-4` rows.

The system SHALL express `年級` as an absolute school-system grade. A junior-high n-th grade SHALL be recorded as grade n plus six; elementary grades are unchanged.

#### Scenario: Junior high grades from a level-relative table

- **WHEN** table `C2-3` is extracted and a junior-high row holds a value in the `一年級` column
- **THEN** the emitted row carries `年級` of `七年級`

##### Example: the same population under both labellings in academic year 114

| Table | Source label | Observed count | Note |
| ----- | ------------ | -------------- | ---- |
| `C2-3` | 國中 `一年級` | 8,469 | excludes the continuing-education division |
| `C2-1` | `七年級` | 8,476 | includes it; the difference of 7 is that division's first grade |

### Requirement: Administrative division names are normalized

The sources spell the same divisions inconsistently across agencies, and the raw workbooks pair each Chinese name with an English one in a single cell. A single spelling rule is needed here because subsequent sources will reuse it.

The system SHALL render administrative division names using `臺` rather than `台`, and SHALL strip the English suffix so that `學校所在地` holds the Chinese name alone.

#### Scenario: A county cell carries a bilingual label

- **WHEN** a source cell holds `臺北市 Taipei City`
- **THEN** `學校所在地` holds `臺北市`

#### Scenario: No variant spellings survive into the long table

- **WHEN** the long table is built
- **THEN** no `學校所在地` value contains `台`
- **AND** no `學校所在地` value contains Latin letters

### Requirement: Cross-table and cross-year invariants hold

Because the C-series tables slice one population, relationships between them are fixed constraints rather than incidental facts, and the system SHALL verify them.

#### Scenario: Tables covering the same population agree

- **WHEN** enrolled student counts are totalled per academic year and per level
- **THEN** the totals derived from `C1-1`, `C1-2`, and `C2-3` are equal for every academic year and level

#### Scenario: School-level tables reconcile to the summary table

- **WHEN** the school-level counts in `C2-1` and `C2-2` are totalled per academic year
- **THEN** each total equals the sum of the corresponding mainstream level and its continuing-education division in `C1-1` for that academic year

##### Example: the reconciliation requires the continuing-education division in academic year 114

| Table | School-level total | `C1-1` mainstream | `C1-1` continuing-ed | Sum |
| ----- | ------------------ | ----------------- | -------------------- | --- |
| `C2-1` (junior high) | 24,536 | 24,513 | 23 | 24,536 |
| `C2-2` (elementary) | 52,058 | 52,051 | 7 | 52,058 |

The school lists in `C2-1` and `C2-2` include continuing-education divisions, whereas `C1-1` reports them in separate columns. Reconciling against the mainstream column alone fails by exactly the continuing-education count.

#### Scenario: Every table code is present in every year

- **WHEN** the long table is grouped by `表號` and `學年`
- **THEN** each of the six table codes has data in all 12 academic years

#### Scenario: Invariant tests detect a seeded fault

- **WHEN** a fault is deliberately injected into any one of the invariants above
- **THEN** the corresponding test fails

### Requirement: Builds are reproducible

The long table SHALL be a deterministic function of the raw workbooks, so that a rebuild can be trusted to reflect source changes rather than run-to-run variation.

#### Scenario: Two consecutive builds agree

- **WHEN** the long table is built twice from an unchanged raw data directory
- **THEN** both runs produce byte-identical output
