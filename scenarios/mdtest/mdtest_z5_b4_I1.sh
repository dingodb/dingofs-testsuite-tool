#!/bin/bash
# mdtest scenario: z=5, b=4, I=1 (multi-branch tree)
mpirun --allow-run-as-root -np ${MDTEST_NP:-16} mdtest -z 5 -b 4 -I 1 -d ./
