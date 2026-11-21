R91 G1STOCK / MS-Turing10M / HISTORICAL H85 STOCK_OFF INVENTORY ONLY / v1

THIS IS NOT A BUILD RUNNER. It never invokes any native PiPNN executable.
It only inspects the existing Ubuntu R90 v1.3 historical Stock binary,
original G1 Fast10M script/manifest, dataset file metadata and resources.
It creates ONE new JSON report; old R85/R90/R91 source, binary, graphs,
Search receipts and BUILD receipts are not modified.

1) Download R91_G1STOCK_READONLY_INVENTORY_v1_BUNDLE.zip into ~/Downloads.
2) Run:
   unzip -n "$HOME/Downloads/R91_G1STOCK_READONLY_INVENTORY_v1_BUNDLE.zip" -d "$HOME/Downloads"
   bash "$HOME/Downloads/R91_G1STOCK_READONLY_INVENTORY_v1_Ubuntu.sh"
3) If output is PASS, the inventory has enough provenance for a manual
   CLI/source review; it is NOT authorization to run Stock10M yet.
4) Send the Ubuntu terminal and the exact new JSON:
   ~/ann-task-a/experiments/R91/r91_g1stock_readonly_preflight_v1/inventory.json

PINNED SOURCE ELFs
stock_off SHA256: 13bef65c01d4638959b16b74fc2b8b6130b433ebc09fff8f436c8b1503e688c9
fast_off SHA256:  fcfb16d0ca2b498f94db8383dfc311c2e7ba88cb3036281accd5f30c6d876793
Historical compiled_manifest.json expected at:
  ~/ann-task-a/experiments/R90/r90_p0a_v13_historical_highway_6bc2_controlled_v1/compile_manifest.json
Existing R91 G1 manifest SHA:
  bd46f8327e634e05ebdf3975c602d3c069df749be8dc3a6e140f286a606e3835

No 10M graph construction, deletion, cgroup runs, or subprocesses outside
reading native system information. On failure, preserve report and STOP.
The Python script will report HOLD if original stock ELF or original G1
source cannot be found and SHA-verified: do not bypass HOLD.
