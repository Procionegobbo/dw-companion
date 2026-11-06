# 009-evals-runner-and-first-reports-001-dataset-schema-rlabel-gate-and-config

**Spec:** STORIES/SPECS/009-evals-runner-and-first-reports.md

**As a** project owner (experienced GM) measuring the assistant
**I want** eval datasets and configs to be loaded through a strict validating loader with a reviewed-label gate
**So that** no eval can ever run on labels I have not reviewed, and every config is checked before any money is spent

## Acceptance Criteria

```gherkin
Feature: Dataset schema, R-LABEL gate and config loader

  Scenario: All rows reviewed passes the gate
    Given a loaded dataset whose every row has "reviewed" exactly JSON true
    When ensure_reviewed is called on it
    Then it returns without raising

  Scenario: One unreviewed row is rejected
    Given a dataset of three rows where one row has "reviewed": false
    When ensure_reviewed is called on it
    Then UnreviewedRowsError is raised with count 1 and that row's id
    And the error names the dataset

  Scenario Outline: Anything other than JSON true is unreviewed
    Given a dataset row whose reviewed value is <value>
    When ensure_reviewed is called
    Then UnreviewedRowsError is raised

    Examples:
      | value        |
      | missing key  |
      | "true"       |
      | 1            |
      | null         |

  Scenario: The error lists at most ten ids
    Given a dataset with 12 unreviewed rows
    When ensure_reviewed is called
    Then UnreviewedRowsError has count 12 and exactly 10 ids

  Scenario: A missing or invalid reviewed value is not a schema error
    Given a row that is otherwise schema-valid but lacks the "reviewed" key
    When load_dataset reads the file
    Then no DatasetError is raised for that row

  Scenario: Valid rows load for each dataset
    Given one schema-valid file per dataset (router, rules_qa, move_classification)
    When each is loaded with load_dataset
    Then a Dataset is returned with its name, path, sha256 and cases
    And RulesCase.answerable is true when expected_section_ids is non-empty and false when it is empty

  Scenario Outline: Schema violations raise DatasetError with file and line
    Given a dataset file containing <problem>
    When load_dataset reads it
    Then DatasetError is raised and its message contains "<file>:<line>"

    Examples:
      | problem                                          |
      | an unknown key                                   |
      | a missing message                                |
      | an empty message                                 |
      | a 501-character message                          |
      | a duplicate id                                   |
      | a wrong id prefix                                |
      | an unknown intent                                |
      | an unknown section id                            |
      | the "thanks" section id (not a chunk)            |
      | key facts on an unanswerable row                 |
      | expected sections without key facts              |
      | six key facts                                    |
      | an unknown move id                               |
      | an alternative equal to the expected move id     |
      | duplicate alternatives                           |
      | a blank line                                     |
      | an empty file                                    |

  Scenario: Known ids come from the normalized data
    Given the mini_normalized fixture
    When known_ids_from is called on it
    Then move_ids are the six fixture moves (excluding "no_move")
    And section_ids exclude "moves/empty" and "thanks"

  Scenario: The committed baseline config loads
    Given evals/configs/baseline.toml as specified
    When load_config("baseline", configs_dir) is called
    Then the judge model differs from the answer model
    And graph.retrieval_k is 6
    And sha256 is the SHA-256 of the file

  Scenario: Graph overrides apply and other fields keep defaults
    Given a config whose [graph] table sets only some GraphSettings fields
    When it is loaded
    Then those fields take the configured values and all others keep GraphSettings defaults

  Scenario Outline: Config errors raise ConfigFileError
    Given a config with <problem>
    When load_config is called
    Then ConfigFileError is raised

    Examples:
      | problem                                              |
      | a missing file                                       |
      | invalid TOML                                         |
      | no judge model                                       |
      | an extra model key                                   |
      | judge equal to the answer model (case-insensitive)   |
      | an unknown graph key                                 |
      | retrieval_k = true                                   |
      | retrieval_k = 0                                      |
      | clarify_threshold = 1.5                              |
      | the invalid name "Base Line"                         |

  Scenario: Config models map to the four MODEL_* env vars
    Given a loaded config
    When model_env is called
    Then it returns exactly the four MODEL_* keys with the config's model ids
```

## Technical Notes

- **Rule R-LABEL** (points 1–3) and **D1**: `ensure_reviewed` + `UnreviewedRowsError` live in `evals/datasets.py`; no override of any kind. This story creates the function; its two call sites (`run_datasets`, `main`) are created in later stories.
- **D2**, **D6**, **D17**.
- **Data Model → Dataset files** and **Python types → `evals/datasets.py`** (`DatasetName`, `DATASET_ORDER`, `RouterCase`, `RulesCase`, `MoveCase`, `Case`, `Dataset`, `DatasetError`, `UnreviewedRowsError`, `KnownIds`, `known_ids_from`, `load_dataset`, `ensure_reviewed`) and **`evals/config.py`** (`EvalModels`, `EvalConfig`, `ConfigFileError`, `load_config`, `model_env`).
- **Validation Rules →** all "Any dataset row", "Dataset file", `router`, `rules_qa`, `move_classification` and "Config" rows (including `MAX_MESSAGE_CHARS = 500`).
- **Configuration → Eval config** (name pattern, exact `baseline.toml` content).
- **Impact on Existing Code →** `evals/__init__.py`, `evals/datasets.py`, `evals/config.py`, `evals/configs/baseline.toml`, `evals/tests/__init__.py`, `evals/tests/conftest.py` (no-network guard, D16), `evals/tests/helpers.py`.
- **Testing → Helpers:** this story creates `helpers.py` with `write_jsonl` and the row builders (`router_row`, `rules_row`, `move_row`; `reviewed=True` only in tmp-file fixtures). The remaining helpers are added by the stories whose tests first need them.
- Do not create or modify any file under `evals/datasets/` in this story; test fixtures are written under `tmp_path` only.

## Tests

- `evals/tests/test_datasets.py`: `test_ensure_reviewed_passes_when_all_true`, `test_ensure_reviewed_rejects_false_row`, `test_ensure_reviewed_rejects_missing_key_and_non_bool`, `test_unreviewed_error_lists_at_most_ten_ids`, `test_load_valid_rows_each_dataset`, `test_schema_errors`, `test_known_ids_from_mini_normalized`.
- `evals/tests/test_config.py`: `test_load_baseline_config`, `test_graph_overrides_applied_and_defaults_kept`, `test_config_errors`, `test_model_env_maps_four_vars`.

**Priority:** Critical
**Dependencies:** None
