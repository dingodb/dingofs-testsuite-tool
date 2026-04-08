#!/bin/bash
# mdtest scenario: z=9, b=2, I=1 (deep binary tree)
mpirun --allow-run-as-root -np ${MDTEST_NP:-16} mdtest -z 9 -b 2 -I 1 -d ./
