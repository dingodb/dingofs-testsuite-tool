---
status: awaiting_human_verify
trigger: "dtt -t mdtest produces no report file"
created: 2026-04-28T00:00:00Z
updated: 2026-04-28T00:00:00Z
---

## Current Focus
hypothesis: CONFIRMED - When dtt -t mdtest is run without -s flag, SCENARIO is empty, causing no scenarios to run and no report
test: Trace the code flow when dtt -t mdtest is called without -s
expecting: If SCENARIO is empty, the script should default to running all mdtest scenarios
next_action: Await user verification of the fix

## Symptoms
expected: mdtest report should be generated after running dtt -t mdtest
actual: No report is generated
errors: None specified yet
reproduction: dtt -t mdtest
timeline: Unknown

## Eliminated

## Evidence
- timestamp: 2026-04-28
  checked: dingofs-testsuite-tool script (lines 492-508)
  found: When tool is mdtest and scenario is empty, -s flag is NOT added to entrypoint command
  implication: entrypoint.sh receives empty SCENARIO

- timestamp: 2026-04-28
  checked: entrypoint.sh validate_params (lines 351-363)
  found: For mdtest, scenario validation is skipped (SCENARIO can be empty)
  implication: Empty SCENARIO passes validation

- timestamp: 2026-04-28
  checked: entrypoint.sh get_scenario_paths (lines 489-497)
  found: When scenario="" (empty), it tries to find "/scenarios/mdtest/.sh" which doesn't exist
  implication: No scenarios run because the path is invalid

- timestamp: 2026-04-28
  checked: scenario scripts in /scenarios/mdtest/
  found: Scripts exist: mdtest_z0_n100.sh, mdtest_z5_b4_I1.sh, mdtest_z6_b3_I1.sh, mdtest_z9_b2_I1.sh
  implication: When SCENARIO is "all" or "mdtest", all 4 scenarios should run

- timestamp: 2026-04-28
  checked: dingofs-testsuite-tool after fix
  found: Changed line 495 from `[[ -n "$scenario" ]] && entrypoint_cmd+=(-s "$scenario")` to `local mdtest_scenario="${scenario:-all}"; entrypoint_cmd+=(-s "$mdtest_scenario")`
  implication: When -s is not provided for mdtest, SCENARIO now defaults to "all"

## Resolution
root_cause: In dingofs-testsuite-tool, when tool=mdtest and no scenario is provided (-s not specified), the SCENARIO variable remains empty. This empty SCENARIO is passed to entrypoint.sh which then tries to find scenario script "/scenarios/mdtest/.sh" (empty string + .sh), which doesn't exist. Thus no mdtest scenarios run and no report is generated.
fix: Default SCENARIO to "all" for mdtest when -s is not provided. Changed line 495 in dingofs-testsuite-tool.
verification: Verify the fix by running dtt -t mdtest without -s and checking that all 4 mdtest scenarios run and reports are generated
files_changed: [/mnt/disk5/daigy/dingofs-testsuite-tool/dingofs-testsuite-tool]
