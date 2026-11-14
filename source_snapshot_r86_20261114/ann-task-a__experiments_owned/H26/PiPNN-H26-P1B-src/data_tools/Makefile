include ../algorithms/bench/parallelDefsANN

vec_to_bin : vec_to_bin.cpp
	$(CC) $(CFLAGS) -o vec_to_bin vec_to_bin.cpp $(LFLAGS) 

compute_groundtruth : compute_groundtruth_old.cpp
	$(CC) $(CFLAGS) -o compute_groundtruth compute_groundtruth_old.cpp $(LFLAGS)

compute_groundtruth_eigen : compute_groundtruth.cpp
	$(CC) $(CFLAGS) -I /usr/include/eigen3 -o compute_groundtruth_eigen compute_groundtruth.cpp $(LFLAGS)

compute_knn_edges : compute_knn_edges.cpp
	$(CC) $(CFLAGS) -o compute_knn_edges compute_knn_edges.cpp $(LFLAGS)

compute_range_groundtruth : compute_range_groundtruth.cpp
	$(CC) $(CFLAGS) -o compute_range_groundtruth compute_range_groundtruth.cpp $(LFLAGS) 

crop : crop.cpp
	$(CC) $(CFLAGS) -o crop crop.cpp $(LFLAGS) 

random_sample : random_sample.cpp
	$(CC) $(CFLAGS) -o random_sample random_sample.cpp $(LFLAGS)

analyze_dups_from_gt : analyze_dups_from_gt.cpp
	$(CC) $(CFLAGS) -o analyze_dups_from_gt analyze_dups_from_gt.cpp $(LFLAGS)

deduplicate_dataset : deduplicate_dataset.cpp
	$(CC) $(CFLAGS) -o deduplicate_dataset deduplicate_dataset.cpp $(LFLAGS)

analyze_dups : analyze_dups.cpp
	$(CC) $(CFLAGS) -o analyze_dups analyze_dups.cpp $(LFLAGS)

dedup_nohashing : dedup_nohashing.cpp
	$(CC) $(CFLAGS) -o dedup_nohashing dedup_nohashing.cpp $(LFLAGS)