## ADDED Requirements

### Requirement: Emit a district-level population long table

The system SHALL emit one long table covering every retrieved period at district granularity.

Each row SHALL carry the columns `期別`, `縣市`, `鄉鎮市區`, `身分別`, `族別`, `性別`, and `人數`. Every column SHALL be non-empty on every row, because each dimension applies to every row of this source.

#### Scenario: Values conform to declared types

- **WHEN** the long table is read
- **THEN** `期別` holds integers denoting the ROC year and month
- **AND** `人數` holds non-negative integers
- **AND** `身分別` holds one of the plains, mountain, or plains-plain status values
- **AND** `性別` holds either the male or the female value

#### Scenario: The long table matches the retrieval records

- **WHEN** the long table is built
- **THEN** the set of periods in the table equals the set of periods holding a retrieval record

##### Example: figures the long table must reproduce for period 11507

| Quantity | Value |
| -------- | ----: |
| districts | 368 |
| national total | 638,466 |
| plains indigenous | 298,327 |
| mountain indigenous | 340,139 |
| plains-plain indigenous | 0 |

### Requirement: Normalize people names across the source revision

At period 11412 the source renamed its column prefix and changed the romanisation of three peoples to their own endonyms. A build keyed to either spelling would silently read empty values for those peoples on the other side of the revision.

The system SHALL record people names in Chinese as the canonical value, and the registry SHALL map every source spelling to that canonical value. A source column the registry does not describe SHALL be a blocking error, because it may indicate a further revision.

#### Scenario: The same people appears under both spellings

- **WHEN** periods from either side of the revision are built
- **THEN** the `族別` values form one consistent set across all periods
- **AND** no `族別` value contains Latin letters

##### Example: spellings that map to one canonical value

| Chinese name | Spelling before 11412 | Spelling from 11412 |
| ------------ | --------------------- | ------------------- |
| 鄒族 | `tsou` | `cou` |
| 卑南族 | `puyuma` | `pinuyumayan` |
| 拉阿魯哇族 | `hlaaluaavu` | `hlaalua` |

#### Scenario: An undescribed column appears

- **WHEN** a period holds a data column the registry does not describe
- **THEN** the system reports the period and the column name
- **AND** no output is written for that period

### Requirement: Emit plains-plain rows only for periods that carry them

Periods before 11412 carry no plains-plain columns at all, whereas periods from 11412 carry them holding zero. The two are different statements: the earlier periods do not report the dimension, while the later ones report it as zero.

Filling zero for the earlier periods would assert something the source never said, and the distinction would not be recoverable from the long table.

The system SHALL emit rows whose `身分別` is the plains-plain value only for periods whose source carries those columns.

#### Scenario: A period predating the revision

- **WHEN** a period before 11412 is built
- **THEN** no row carries the plains-plain status value

#### Scenario: A period carrying the columns at zero

- **WHEN** period 11507 is built
- **THEN** rows carry the plains-plain status value
- **AND** their `人數` is 0

#### Scenario: Plains-plain columns appear earlier than declared

- **WHEN** a period before 11412 is found to carry plains-plain columns
- **THEN** the system reports the period and stops, because this contradicts the registry

##### Example: the boundary measured across sampled periods

| Period | Column count | Plains-plain columns | Plains-plain rows emitted |
| ------ | -----------: | -------------------- | ------------------------- |
| 11401 | 115 | absent | none |
| 11412 | 162 | present, holding zero | emitted with `人數` 0 |
| 11507 | 162 | present, holding zero | emitted with `人數` 0 |

### Requirement: Exclude aggregate columns from the long table

The source supplies totals alongside the per-people detail, and those totals are exactly derivable from it. Including them would make any unfiltered aggregation overcount.

The system SHALL emit only the finest combination of people, sex, and status. Totals SHALL be used for verification and SHALL then be discarded.

#### Scenario: No total rows survive

- **WHEN** the long table is built
- **THEN** no row represents a total across peoples, sexes, or statuses

#### Scenario: Summing one period reproduces the source total

- **WHEN** one period is summed across every dimension
- **THEN** the result equals the national total the source reported for that period

### Requirement: Cross-period invariants hold

Because the same population is sliced by people and by status, relationships between those slices are fixed constraints rather than incidental facts.

#### Scenario: Slices of one period agree

- **WHEN** a period is totalled by `族別` and separately by `身分別`
- **THEN** the two totals are equal

#### Scenario: People labels do not split across the revision

- **WHEN** the long table is grouped by `族別`
- **THEN** the label set for periods before 11412 equals the label set for periods from 11412, excluding the plains-plain peoples

#### Scenario: Administrative names use the orthodox form

- **WHEN** the long table is built
- **THEN** no `縣市` or `鄉鎮市區` value contains the variant form of the character for Taiwan

#### Scenario: Invariant tests detect a seeded fault

- **WHEN** a fault is injected into the people-versus-status equality or into the plains-plain period boundary
- **THEN** the corresponding test fails

### Requirement: Builds are reproducible and offline

The long table SHALL be a deterministic function of the persisted retrieval results, and building SHALL NOT perform any network request.

#### Scenario: Two consecutive builds agree

- **WHEN** the long table is built twice from unchanged inputs
- **THEN** both runs produce byte-identical output

#### Scenario: Building without network access

- **WHEN** every required period is present on disk
- **THEN** the build completes without issuing a network request
