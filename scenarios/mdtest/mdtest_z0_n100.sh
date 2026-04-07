#!/bin/bash
# mdtest scenario: z=0, n=100 (flat directory)
mpirun --allow-run-as-root -np 32 mdtest -d ./test -z 0 -F -n 100
