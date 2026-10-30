`-fixed_leaders <k>` gives a fixed number of leaders in each subproblem. Pick 2 for HCNNG. This will not play nicely with fanout greater than `k`.

`-no_reservoir` will turn off the online pruning, allowing the intermediate graph to be unbounded in size. Do not use this in memory constrained environments. Do use this if you want a modest speedup. 

