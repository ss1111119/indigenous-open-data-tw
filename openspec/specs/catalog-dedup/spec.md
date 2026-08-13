# catalog-dedup Specification

## Purpose

TBD - created by archiving change 'dedupe-odportal-catalog'. Update Purpose after archive.

## Requirements

### Requirement: Group cross-listed datasets by connected components

The catalog records a single partner id per entry in its shared-resource column. Pairing entries two at a time works only while every duplicate group has exactly two members; three mutually-pointing entries would silently produce contradictory merges, where A merges with B and B merges with C while A and C land in separate rows.

The system SHALL group entries by connected components over the shared-resource pointers, and SHALL treat a group larger than two members as a blocking error, because the merge rules were derived from measurements of two-member groups only.

#### Scenario: The catalog groups into pairs and singletons

- **WHEN** the 763-entry catalog is grouped
- **THEN** 603 groups have one member and 80 groups have two
- **AND** the deduplicated output holds 683 rows

#### Scenario: A shared-resource pointer leaves the catalog

- **WHEN** a shared-resource pointer names an id absent from the input catalog
- **THEN** the system reports that id and the row that referenced it
- **AND** no output is written

#### Scenario: A group exceeds two members

- **WHEN** connected components produce a group of three or more entries
- **THEN** the system reports the group's members
- **AND** no output is written

---
### Requirement: Merge resources as a union

Neither platform holds a superset of the other. Measured across the 80 duplicate pairs, 46 pairs have resources present on one side and absent on the other in both directions, and platform precedence is not a usable rule because the richer side is the national platform in roughly half the pairs and the local portal in the rest.

The system SHALL set a merged entry's resources to the union of its members' resource URLs, and SHALL recount the resource-count columns from that union.

#### Scenario: Both members contribute unique resources

- **WHEN** two members of a group each hold resource URLs the other lacks
- **THEN** the merged row's resource set contains every URL from both members

#### Scenario: No resource is lost across the whole catalog

- **WHEN** the deduplicated output is produced
- **THEN** the union of all resource URLs in the output equals the union of all resource URLs in the input, with no additions and no omissions

#### Scenario: Union smaller than a member

- **WHEN** a computed union holds fewer URLs than any single member of its group
- **THEN** the system reports the group and stops, because the union logic is wrong

##### Example: choosing one side would discard most resources

| Dataset | National platform | Local portal | Union |
| ------- | ----------------: | -----------: | ----: |
| `10730-09-01-2 臺中市原住民權益及福利宣導統計` | 183 | 18 | 183 |
| `30220-09-01-2 臺中市輔導原住民職業訓練及就業服務統計` | 182 | 18 | 182 |
| `10122-00-04-2 臺中市各區 現住人口數按性別及原住民身分分` | 141 | 18 | 141 |

---
### Requirement: Resolve field conflicts by measured rule

Each merge rule follows from the observed conflict distribution across the 80 pairs rather than from preference. Where the distribution admits no exception, a deviation SHALL be a blocking error rather than a silent fallback.

The system SHALL resolve each field as follows: take the populated side for the providing agency; take the name from the side whose providing agency is populated; join and sort the union for source platform and for format; prefer the specific value over `UNKNOWN` or empty for licence; take the later value for last-updated; and take the more usable value for grade.

#### Scenario: Providing agency is populated on exactly one side

- **WHEN** a group's two members are merged
- **THEN** the merged row takes the non-empty providing agency
- **AND** the merged row's providing agency is non-empty

#### Scenario: Providing agency is populated on both sides and differs

- **WHEN** both members hold different non-empty providing agencies
- **THEN** the system reports both values and stops, because the measured distribution holds no such case

##### Example: measured conflict distribution across the 80 pairs

| Field | Identical | Populated on one side only | Both populated and differing |
| ----- | --------: | -------------------------: | ---------------------------: |
| providing agency | 0 | 80 | 0 |
| grade | 79 | 0 | 1 |
| name | 74 | 0 | 6 |
| licence | 73 | 1 | 6 |
| source platform | 0 | 0 | 80 |
| format | 40 | 0 | 40 |

##### Example: source platform is preserved rather than resolved

- **GIVEN** one member is listed on `政府開放資料平臺` and the other on `臺中市政府`
- **WHEN** the pair is merged
- **THEN** the merged row's source platform holds both values joined and sorted

---
### Requirement: Flag rows whose grade does not cover the merged resources

Grading sampled at most two representative resources per dataset, so a merged row whose union is larger than either member's original resource set carries grade columns that were never evaluated against the added resources. Re-probing would mean another round of requests to government servers and would make the grades disagree with the already-published grading report.

The system SHALL carry a boolean column that is true exactly for rows whose union exceeds every member's original resource count, and SHALL NOT perform any network request.

#### Scenario: Merged row gained resources beyond both members

- **WHEN** a group's union holds more URLs than either member held alone
- **THEN** that row's grade-coverage flag is true

#### Scenario: Flag count matches the measured figure

- **WHEN** the deduplicated output is produced
- **THEN** exactly 23 rows carry a true grade-coverage flag

#### Scenario: Deduplication performs no network access

- **WHEN** deduplication runs
- **THEN** no network request is issued

---
### Requirement: Merged rows record their provenance

Collapsing two catalog entries into one destroys the ability to trace a row back to the platforms it came from unless the identifiers are retained.

The system SHALL carry a merged-count column and a merged-source column holding every member identifier, so that any merged row can be traced back to its inputs.

#### Scenario: A merged row names its members

- **WHEN** a two-member group is merged
- **THEN** the merged-count column holds 2
- **AND** the merged-source column holds both member identifiers, joined and sorted

#### Scenario: An unmerged row still records provenance

- **WHEN** a single-member group is written
- **THEN** the merged-count column holds 1
- **AND** the merged-source column holds that entry's own identifier

#### Scenario: Merged counts reconcile to the input

- **WHEN** the deduplicated output is produced
- **THEN** exactly 80 rows hold a merged count of 2
- **AND** the merged counts sum to 763

---
### Requirement: Deduplication is reproducible

The output SHALL be a deterministic function of its inputs, so that a rerun can be trusted to reflect input changes rather than run-to-run variation.

#### Scenario: Two consecutive runs agree

- **WHEN** deduplication runs twice over unchanged inputs
- **THEN** both runs produce byte-identical output

#### Scenario: Invariant tests detect a seeded fault

- **WHEN** a fault is injected into the resource-preservation invariant or the row-count invariant
- **THEN** the corresponding test fails
