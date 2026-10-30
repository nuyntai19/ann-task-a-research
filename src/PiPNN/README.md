# PiPNN

PiPNN is a new nearest-neighbor search algorithm built as part of the ParlayANN library of approximate nearest neighbor search algorithms. It is written in C++ and uses parallel primitives from [ParlayLib](https://cmuparlay.github.io/parlaylib/). 

To install, [clone the repo](https://github.com/cmuparlay/ParlayANN/tree/main) and then initiate the ParlayLib submodule:

```bash
git submodule init
git submodule update
```

Then build with CMAKE via:

```bash
mkdir build && cd build
cmake ../ -DCMAKE_BUILD_TYPE=Release
```

Now you can build PiPNN via:

```bash
cd algorithms/PipNN
make
```

Which will build binaries for each combination of data type (FLOAT, INT8, UINT8) and dissimilarity measure (EUCLIDEAN, MIPS). You can then run PiPNN as in the following example on SPACE 100M:

```bash
./build/algorithms/PipNN/neighbors-pipnn_INT8_T_EUCLIDEAN -base_path data/MSSPACEV1B/spacev1b_base.i8bin.crop_nb_100000000 -graph_outfile data/MSSPACEV1B/msspacev-gt-100M.pipnn -query_path data/MSSPACEV1B/query.i8bin -gt_path data/MSSPACEV1B/msspacev-gt-100M -presearch -vary_degree -file_type bin -alpha 1.13 -num_clusters 1 -fanout 30 -fanout_scheme 10,3 -cluster_size 1024 -mst_deg 2 -multi_pivot -prune -prune_all -prune_degree 64 -k 10 -top_level_leaders 1000 -fraction_leaders 0.005 -hash_bits 12 -leaf_method EigenKNN
```

Optimized alpha parameters for many datasets can be found in algorithms/vamana/scripts. We always use the same alpha parameter as Vamana uses, but oherwise the above hyper-parameters are sane defaults which always perform well. 

Supplement pdf for the paper is here: PiPNN_Paper_Draft_sup.pdf
