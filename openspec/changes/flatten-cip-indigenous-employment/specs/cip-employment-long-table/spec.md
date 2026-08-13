## ADDED Requirements

### Requirement: Emit an employment long table across the usable years

The system SHALL emit one long table covering the usable statistical years, flattening the source's wide measure columns into a base-by-status-by-sex shape.

Each row SHALL carry the columns `年度`, `主題`, `切法`, `類別`, `項目別`, `性別`, `狀態`, `人數`, `百分比`, and `樣本數`. The dimension columns SHALL be non-empty on every row. The three measure columns MAY be empty, because the source itself publishes empty cells.

#### Scenario: The long table covers exactly the usable years

- **WHEN** the long table is built
- **THEN** the set of `年度` values is 103, 104, 105, 108, 109, 110, 111, and 112
- **AND** no row carries year 106 or year 107

##### Example: why two years are absent for different reasons

| Year | Present in source | In long table | Reason |
| ---- | ----------------- | ------------- | ------ |
| 106 | yes | **no** | rows are misaligned — excluded by decision |
| 107 | **no** | no | the source does not publish it |

#### Scenario: Counts are not integers

- **WHEN** `人數` is read
- **THEN** it holds a floating-point value, because the source publishes sampled estimates rather than counts

### Requirement: Status values follow the topic

The two topics divide their base population differently: labour-force participation splits into in and out of the labour force, whereas employment status splits into employed and unemployed. A single shared status vocabulary would conflate them.

The registry SHALL declare the legal status values per topic, and a status value it does not declare SHALL be a blocking error.

#### Scenario: Each topic carries its own two statuses

- **WHEN** the long table is grouped by `主題` and `狀態`
- **THEN** the labour-force-participation topic carries exactly its two declared statuses
- **AND** the employment-status topic carries exactly its two declared statuses
- **AND** no status value appears under both topics

##### Example: the parallel structure of the two topics

| Topic | Base column in source | Statuses |
| ----- | --------------------- | -------- |
| 勞動力參與情形 | `年紀15歲以上民間人口` | 勞動力, 非勞動力 |
| 就失業情形 | `勞動力人口` | 就業, 失業 |

### Requirement: Aggregate totals are verified then discarded

The source publishes a total across statuses and a total across sexes alongside the detail. Both are exactly the sums of the detail, so including them would make any unfiltered aggregation overcount.

The system SHALL emit only the finest status-by-sex combinations, and SHALL use the totals for verification before discarding them.

#### Scenario: No total rows survive

- **WHEN** the long table is built
- **THEN** no row carries a total value in `狀態`
- **AND** no row carries a total value in `性別`

#### Scenario: Percentages cannot be recovered by summation

- **WHEN** a reader sums `百分比` across statuses
- **THEN** the result is not a meaningful rate, because the totals were discarded and percentages do not add

### Requirement: Aggregate identities hold within a measured tolerance

This source publishes sampled estimates rounded to whole people, so its own totals do not equal the sum of its detail exactly. Requiring exact equality would reject every usable year; requiring nothing would let a misaligned year through.

The system SHALL verify each identity to an absolute tolerance of ten people, SHALL record the largest observed difference per year, and SHALL treat an excess as a blocking error.

#### Scenario: A usable year passes within tolerance

- **WHEN** a usable year is verified
- **THEN** the difference between the published total and the sum of its detail is at most ten people for every row

##### Example: largest observed difference for the sex identity, per year

| Year | Largest difference | Reading |
| ---- | -----------------: | ------- |
| 103 | 0.01 | rounding |
| 104 | 0.01 | rounding |
| 105 | 8.00 | rounding, 0.006 percent of 127,199 |
| 108 | 0.00 | exact |
| 109 | 0.00 | exact |
| 110 | 0.01 | rounding |
| 111 | 0.00 | exact |
| 112 | 1.00 | rounding |
| **106** | **117,516.09** | **misaligned, excluded** |

#### Scenario: The excluded year still fails its identities

- **WHEN** year 106 is verified
- **THEN** its identity differences exceed the tolerance
- **AND** if they did not, the system reports that the exclusion rationale is contradicted and stops

#### Scenario: An identity exceeds the tolerance in a usable year

- **WHEN** a usable year holds a difference above ten people
- **THEN** the system reports the year, category, item, identity, and difference
- **AND** no output is written

### Requirement: The response envelope is validated before parsing

The source wraps its payload two levels deep. Reading it as a plain list of records yields a single row holding the envelope keys rather than the data, which would silently produce a one-row table.

The system SHALL validate that the response carries the expected envelope, and SHALL treat a departure as a blocking error naming the actual top-level keys.

#### Scenario: The envelope is as expected

- **WHEN** a dataset is retrieved
- **THEN** the records are read from inside the envelope
- **AND** the field definitions are read from the same envelope

#### Scenario: The envelope changes shape

- **WHEN** the response does not carry the expected envelope
- **THEN** the system reports the actual top-level keys and stops

### Requirement: Sample sizes are retained

The table reports sampled estimates, so a figure without its sample size cannot be judged for reliability. The source leaves some sample sizes empty.

The system SHALL carry `樣本數` on every row and SHALL NOT drop rows whose sample size is empty.

#### Scenario: Sample size accompanies every row

- **WHEN** the long table is read
- **THEN** every row carries a `樣本數` column
- **AND** rows whose sample size is empty are still present

### Requirement: Builds are reproducible and offline

The long table SHALL be a deterministic function of the persisted retrieval results, and building SHALL NOT perform any network request.

#### Scenario: Two consecutive builds agree

- **WHEN** the long table is built twice from unchanged inputs
- **THEN** both runs produce byte-identical output

#### Scenario: Invariant tests detect a seeded fault

- **WHEN** a fault is injected into the year-exclusion check or into the no-totals check
- **THEN** the corresponding test fails
