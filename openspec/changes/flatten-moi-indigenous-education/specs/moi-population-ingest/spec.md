## MODIFIED Requirements

### Requirement: Verify every period before discarding detail

Detail is discarded, so verification cannot be repeated later. Verifying after aggregation would check only the sums the system itself computed, which cannot detect a source inconsistency.

Not every dataset on this API carries aggregates to check against. `ODRP018` supplies totals alongside its per-people detail, whereas `ODRP026` is already in long form and publishes no total or subtotal value at all. Requiring aggregate identities unconditionally would leave the second case discarding village detail with no guarantee established.

The system SHALL establish a verification guarantee against every village row before aggregating, and SHALL stop on any mismatch. Where the source carries its own aggregates, that guarantee SHALL be the aggregate identities. Where it does not, the guarantee SHALL be dimension cross-product completeness: every village SHALL carry exactly the number of rows implied by the dataset's dimension sizes for that period.

For datasets carrying aggregates, the per-people column list differs by status and SHALL be taken from the registry per status rather than shared: the plains and mountain statuses each carry 17 peoples, the plains-plain status carries 12, and the top level carries their union of 27.

#### Scenario: All seven identities hold for a dataset carrying aggregates

- **WHEN** a period's village rows are verified and the source carries aggregates
- **THEN** each row's total equals its male plus female counts
- **AND** each row's total equals the sum of its status subtotals
- **AND** each row's total equals the sum of its per-people counts across the union of peoples
- **AND** each status subtotal equals the sum of the per-people counts of that status's own people list
- **AND** each people's top-level count equals the sum of that people's counts across the statuses that carry it

##### Example: identities verified at period 11507 of `ODRP018`

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

#### Scenario: Cross-product completeness holds for a dataset without aggregates

- **WHEN** a period's village rows are verified and the source carries no aggregate value
- **THEN** the row count equals the number of villages multiplied by the product of the dimension sizes for that period
- **AND** a period failing that equality has its absent or surplus dimension combination reported

##### Example: cross-product completeness measured on `ODRP026`

| Year | Source rows | Rows per village | Whole multiple |
| ---- | ----------: | ---------------: | -------------- |
| 106 | 722,292 | 92 | yes — 7,851 villages |
| 112 | 712,816 | 92 | yes — 7,748 villages |
| 113 | 712,815 | 92 | no — one row short |
| 114 | 1,069,776 | 138 | yes — 7,752 villages |

#### Scenario: An identity fails

- **WHEN** any identity does not hold for a village row
- **THEN** the system reports the period, the district code, the failing identity, and the difference
- **AND** neither the aggregated result nor the retrieval record is written for that period

## ADDED Requirements

### Requirement: Cross-dataset village counts are reconciled

Two datasets from the same agency covering the same year should describe the same villages. Comparing them is the only check available that does not rely on a single dataset's internal consistency.

The system SHALL compare a period's village count against the village count of another dataset for the same year, and SHALL record the comparison. A mismatch SHALL be a warning rather than a blocking error, because administrative boundary changes can make two datasets differ legitimately when their reference months differ.

#### Scenario: The counts agree

- **WHEN** a year's village count is compared against the other dataset
- **THEN** the retrieval record states both counts and that they agree

##### Example: counts measured across the two datasets

| `ODRP026` year | Villages implied | `ODRP018` period | Villages | Agree |
| -------------- | ---------------: | ---------------- | -------: | ----- |
| 112 | 7,748 | 11306 | 7,748 | yes |
| 114 | 7,752 | 11412 | 7,752 | yes |

#### Scenario: The counts differ

- **WHEN** the two village counts differ
- **THEN** the system reports both counts and the periods compared
- **AND** the retrieval record notes the difference
- **AND** retrieval continues
