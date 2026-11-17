TASK D handoff metadata — generated after SHA PASS for all 12 files.

These exports DO NOT contain dataset or graph binaries. The file relative_paths_for_rsync.txt
lists exactly 3 datasets and 9 ORIGINAL index.graph paths under ~/ann-task-a.
To transfer to a mounted drive, use:
  rsync -av --files-from="<EXPORT>/relative_paths_for_rsync.txt" "$HOME/ann-task-a/" "/media/<DRIVE>/TaskD/"
Then copy this export metadata folder alongside, and SHA-check on recipient host.
Original graph extension is .graph, not .pipnn; do not rename/convert before loader verification.
GT uses split int32 ID / float32 squared-L2 arrays after an int32 n,k header.
Builder binaries SHA recorded in expected_artifacts.csv, but the binary files have NOT been exported.
Source branch/commit in provenance_current_checkout.json represents CURRENT checkout only,
NOT verified historical builder source unless matched with pinned build receipts.
Seed is NOT_PINNED_OR_NOT_RECORDED_IN_PILOT_RECEIPT (E_PROTOCOL). No seed invented.
Raw receipts tar includes available small file receipts ONLY from 9 formal graph folders;
review receipt_completeness.json and supplement missing build/Search receipts.
IMPORTANT: only run full SHA, tar, and rsync AFTER G11 benchmark is finished.
