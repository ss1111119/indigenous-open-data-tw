# moi-population-ingest Specification

## Purpose

TBD - created by archiving change 'flatten-moi-indigenous-population'. Update Purpose after archive.

## Requirements

### Requirement: Retrieve each period page by page

The source paginates at 2,000 rows per page and reports both a total row count and a page count. Reading only the first page would silently truncate roughly three quarters of every period.

The system SHALL request every page reported for a period, and SHALL treat a mismatch between the rows actually collected and the total the source reported as a blocking error.

#### Scenario: A period is retrieved completely

- **WHEN** a period is retrieved
- **THEN** every page the source reports is requested
- **AND** the number of rows collected equals the total the source reported

##### Example: page structure measured at period 11507

| Page | Rows returned |
| ---- | ------------: |
| 1 | 2,000 |
| 2 | 2,000 |
| 3 | 2,000 |
| 4 | 1,781 |
| **Total** | **7,781** |

#### Scenario: Collected rows do not match the reported total

- **WHEN** the rows collected for a period differ from the total the source reported
- **THEN** the system reports the period, both counts, and stops

---
### Requirement: Distinguish an unpublished period from a failed request

Publication lags by roughly two months, so a period beyond the published range is a normal boundary rather than an error. Conflating it with a network failure would either hide real failures or stop retrieval at the frontier every month.

The system SHALL distinguish a source response of no-data from a transport or server failure, and SHALL report which of the two occurred for every period it could not retrieve.

#### Scenario: The requested period is not yet published

- **WHEN** a period returns the source's no-data response
- **THEN** the system records that period as unpublished
- **AND** retrieval of the remaining periods continues

#### Scenario: A request fails in transport

- **WHEN** a request fails for a reason other than the no-data response
- **THEN** the system reports the period and the failure
- **AND** the period is not recorded as unpublished

##### Example: the frontier measured on 2026-08-13

| Period | Source response |
| ------ | --------------- |
| 11507 | data returned, 7,781 rows |
| 11508 | no data — not yet published |

---
### Requirement: Aggregate to district level and discard village detail

The project's ethical boundary places published output at district level; village-level figures are not redistributed. Village rows are small enough to identify individuals: of 7,524 non-empty village rows at period 11507, 1,897 hold fewer than ten people, and the village-by-people-by-sex cells hold 32,936 values of one or two. Aggregating to district leaves only 2 of 368 rows below ten.

Retaining village detail would serve only the ability to publish a finer granularity, which the project has committed never to do.

The system SHALL aggregate each period to district level in memory and SHALL persist only the aggregated result. Village-level rows SHALL NOT be written to disk.

#### Scenario: Only aggregated rows are persisted

- **WHEN** a period has been retrieved and verified
- **THEN** the persisted result holds one row per district and dimension combination
- **AND** no persisted file contains a village identifier

#### Scenario: Aggregation preserves the period total

- **WHEN** period 11507 is aggregated
- **THEN** the aggregated rows cover 368 districts
- **AND** the total across all districts is 638,466

---
### Requirement: Verify every period before discarding detail

Detail is discarded, so verification cannot be repeated later. Verifying after aggregation would check only the sums the system itself computed, which cannot detect a source inconsistency.

The system SHALL evaluate the source's own aggregate identities against every village row before aggregating, and SHALL stop on any mismatch.

The per-people column list differs by status and SHALL be taken from the registry per status rather than shared: the plains and mountain statuses each carry 17 peoples, the plains-plain status carries 12, and the top level carries their union of 27.

#### Scenario: All seven identities hold

- **WHEN** a period's village rows are verified
- **THEN** each row's total equals its male plus female counts
- **AND** each row's total equals the sum of its status subtotals
- **AND** each row's total equals the sum of its per-people counts across the union of peoples
- **AND** each status subtotal equals the sum of the per-people counts of that status's own people list
- **AND** each people's top-level count equals the sum of that people's counts across the statuses that carry it

##### Example: identities verified at period 11507

| Identity | Result |
| -------- | ------ |
| A — total equals male plus female | holds for all 7,781 rows |
| B — total equals plains plus mountain plus plains-plain subtotals | holds for all 7,781 rows |
| C — total equals the union of 27 per-people columns | holds for all 7,781 rows |
| D — plains subtotal equals its 17 per-people columns | holds for all 7,781 rows |
| E — mountain subtotal equals its 17 per-people columns | holds for all 7,781 rows |
| F — plains-plain subtotal equals its 12 per-people columns | holds for all 7,781 rows |
| G — each people's top level equals its sum across statuses | holds for all 7,781 rows |
| national total 638,466 equals 298,327 plus 340,139 plus 0 | exact |

##### Example: why identity C counts the union rather than 17

- **GIVEN** the top level carries 27 peoples while plains and mountain carry 17 each
- **AND** the 10 peoples unique to the plains-plain status currently hold zero
- **WHEN** the total is compared against only the 17 shared peoples
- **THEN** the comparison holds today but SHALL fail once plains-plain counts become non-zero, which is why the union is the checked quantity

#### Scenario: An identity fails

- **WHEN** any identity does not hold for a village row
- **THEN** the system reports the period, the district code, the failing identity, and the difference
- **AND** neither the aggregated result nor the retrieval record is written for that period

---
### Requirement: Record what was retrieved and verified

Because village detail is discarded, the aggregated figures would otherwise be assertions with no traceable basis.

The system SHALL write a retrieval record per period holding the period, the total the source reported, the rows collected, the page count, the district count after aggregation, the outcome of each identity check, the column-name version detected, and the retrieval time.

#### Scenario: A retrieval record accompanies every persisted period

- **WHEN** a period's aggregated result is written
- **THEN** a retrieval record for that period is written alongside it
- **AND** the record states which column-name version the period used

#### Scenario: Retrieval is repeatable

- **WHEN** retrieval runs again and a period already has a complete retrieval record
- **THEN** that period is not requested again
