"""Audit hashes, query isolation, routing budgets and benchmark coverage after all stages."""
import argparse
import json
from common import EXP, HERE, SEEDS, rows, save, sha
from compare_stages import FOLDERS


def verify(name):
    data=HERE/"runs"/name/"data"
    groups=[set(map(int,(data/(key+".ids")).read_text().split()))
            for key in ("selection","cal","proxy")]
    if [len(g) for g in groups]!=[8192,1024,3072] or any(
        groups[i]&groups[j] for i,j in ((0,1),(0,2),(1,2))):
        raise ValueError("Query split overlap")
    validated={}
    digests={}
    for i,folder in enumerate(FOLDERS,1):
        run=EXP/folder/"runs"/name
        manifest=json.loads((run/"manifest.json").read_text())
        counts=json.loads((run/"validation.json").read_text())
        if counts["status"]!="PASS":
            raise ValueError(f"Stage {i} failed")
        from pathlib import Path
        for key in ("inputs_sha256","configs_sha256","graphs_sha256"):
            for path,expected in manifest[key].items():
                if path not in digests:
                    digests[path]=sha(Path(path))
                if digests[path]!=expected:
                    raise ValueError(f"Input changed: {path}")
        survey=rows(run/"survey.csv")
        timing=rows(run/"timing.csv")
        if len(survey)!=counts["cases"]*len(manifest["grid"]) or len(timing)!=counts["timing_rows"]:
            raise ValueError(f"Incomplete stage {i}")
        for r in survey:
            calc=float(r["route_cmps"])
            if i<4:
                expected=0 if r["arm"]=="node0" else 32
            else:
                expected=12 if r["arm"] in ("flat12","hier8x4") else 32
            if calc!=expected:
                raise ValueError(f"Wrong route budget: {r['arm']} {calc}")
            if i==2 and r["arm"]=="top2" and float(r["two_fraction"])<.99:
                raise ValueError("Top-2 fails to use two entries")
        validated[str(i)]={**counts,"survey_rows":len(survey),"timing_repeats":manifest["timing_repeats"]}
    if len(rows(EXP/FOLDERS[2]/"runs"/name/"build.csv"))!=9:
        raise ValueError("Expected nine rebuilt graphs at stage 3")
    save(EXP/f"routing_{name}_validation.json",{"status":"PASS","stages":validated,
         "unique_artifact_hashes_checked":len(digests),"disjoint_query_roles":True})
    print("ALL_FOUR_ROUTING_STAGES_VERIFIED")


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name",default="sift1m_r1")
    verify(parser.parse_args().name)
