#!/bin/bash
# mdtest scenario: z=6, b=3, I=1 (medium deep tree)
mpirun --allow-run-as-root -np 32 mdtest -z 6 -b 3 -I 1 -d ./
