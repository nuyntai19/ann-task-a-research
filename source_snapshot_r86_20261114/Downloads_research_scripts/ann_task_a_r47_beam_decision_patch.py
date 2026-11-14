#!/usr/bin/env python3
"""R47: trace beam decisions in a separate ParlayANN tree. Not a validated experiment."""
import argparse
import json
from pathlib import Path


def replace_first(s, old, new, name):
    if old not in s:
        raise ValueError(f"Missing anchor {name}; refusing to modify source")
    return s.replace(old, new, 1)


def patch(s, qids):
    if 'R47_BEGIN' in s:
        raise ValueError('R47 markers already present; refusing to patch twice')
    s = replace_first(s, '#include <queue>\n',
        '#include <queue>\n#include <array>\n#include <sstream>\n#include <iostream>\n', 'includes')
    ctx = '''  hashset<indexType> has_been_seen(2 * (10 + beamSize) * max_degree);

  // R47: diagnostic instrumentation; original search decisions are untouched.
  const std::array<long long, %d> r47_query_ids = {%s};
  const long long r47_qid = static_cast<long long>(p.id());
  const bool r47_trace = std::find(r47_query_ids.begin(), r47_query_ids.end(), r47_qid)
                         != r47_query_ids.end();
  std::ostringstream r47_log;
  if (r47_trace) r47_log << "R47_BEGIN q=" << r47_qid
                         << " beam=" << beamSize << " limit=" << QP.limit
                         << " degree_limit=" << QP.degree_limit << "\\n";
''' % (len(qids), ', '.join(map(str,qids)))
    s = replace_first(s,
        '  hashset<indexType> has_been_seen(2 * (10 + beamSize) * max_degree);\n',
        ctx, 'context')
    s = replace_first(s,
        '    if (early_stop(frontier, unvisited_frontier, visited, QP))\n      break;\n    \n    G[current.first].prefetch();',
        '''    if (early_stop(frontier, unvisited_frontier, visited, QP)) {
      if (r47_trace) r47_log << "R47_STOP_EARLY q=" << r47_qid << "\\n";
      break;
    }
    if (r47_trace) r47_log << "R47_EXPAND q=" << r47_qid
                           << " node=" << current.first
                           << " distance=" << current.second
                           << " step=" << num_visited << "\\n";
    G[current.first].prefetch();''', 'expansion')
    s = replace_first(s,
        '      if (has_been_seen(a) || Points[a].same_as(p)) continue;  // skip if already seen\n      Q_Points[a].prefetch();\n      pruned.push_back(a);',
        '''      // has_been_seen() may mutate a hashset. Call it precisely once.
      bool r47_was_seen = has_been_seen(a);
      if (r47_was_seen) {
        if (r47_trace) r47_log << "R47_SEEN_SKIP q=" << r47_qid
                               << " from=" << current.first << " node=" << a << "\\n";
        continue;
      }
      if (Points[a].same_as(p)) {
        if (r47_trace) r47_log << "R47_SAME_SKIP q=" << r47_qid
                               << " from=" << current.first << " node=" << a << "\\n";
        continue;
      }
      if (r47_trace) r47_log << "R47_DISCOVER q=" << r47_qid
                             << " from=" << current.first << " node=" << a << "\\n";
      Q_Points[a].prefetch();
      pruned.push_back(a);''', 'neighbor gating')
    s = replace_first(s,
        '      // skip if frontier not full and distance too large\n      if (dist >= cutoff) continue;\n      candidates.push_back(std::pair{a, dist});',
        '''      if (r47_trace) r47_log << "R47_SCORE q=" << r47_qid
                             << " from=" << current.first << " node=" << a
                             << " distance=" << dist << " cutoff=" << cutoff << "\\n";
      // Original cutoff decision, unchanged.
      if (dist >= cutoff) {
        if (r47_trace) r47_log << "R47_CUTOFF_REJECT q=" << r47_qid
                               << " node=" << a << "\\n";
        continue;
      }
      if (r47_trace) r47_log << "R47_STAGE q=" << r47_qid
                             << " node=" << a << "\\n";
      candidates.push_back(std::pair{a, dist});''', 'distance cutoff')
    s = replace_first(s,
        '         offset + 1 < remain)) {\n      offset++;\n      continue;\n    }',
        '''         offset + 1 < remain)) {
      if (r47_trace) r47_log << "R47_BATCH_WAIT q=" << r47_qid
                             << " staged=" << candidates.size()
                             << " offset=" << offset << " remain=" << remain << "\\n";
      offset++;
      continue;
    }''', 'batch wait')
    s = replace_first(s,
        '    // trim to at most beam size\n    new_frontier_size = std::min<size_t>(beamSize, new_frontier_size);\n\n    // copy new_frontier back to the frontier',
        '''    // trim to at most beam size
    new_frontier_size = std::min<size_t>(beamSize, new_frontier_size);

    if (r47_trace) {
      auto r47_in_new_beam = [&](indexType id) {
        for (size_t j = 0; j < new_frontier_size; ++j)
          if (new_frontier[j].first == id) return true;
        return false;
      };
      for (auto it = candidates.begin(); it != candidates_end; ++it) {
        r47_log << (r47_in_new_beam(it->first) ? "R47_MERGE_KEEP" : "R47_MERGE_DROP")
                << " q=" << r47_qid << " node=" << it->first
                << " distance=" << it->second << "\\n";
      }
      for (const auto &old_vertex : frontier) {
        if (!r47_in_new_beam(old_vertex.first))
          r47_log << "R47_BEAM_EVICT q=" << r47_qid
                  << " node=" << old_vertex.first
                  << " distance=" << old_vertex.second << "\\n";
      }
    }

    // copy new_frontier back to the frontier''', 'merge decisions')
    s = replace_first(s,
        '  return std::make_pair(std::make_pair(parlay::to_sequence(frontier),\n                                       parlay::to_sequence(visited)),\n                        full_dist_cmps);\n}',
        '''  if (r47_trace) {
    r47_log << "R47_END q=" << r47_qid << " expanded=" << num_visited
            << " remain=" << remain << " offset=" << offset
            << " full_dist_cmps=" << full_dist_cmps
            << " reason="
            << ((num_visited >= QP.limit) ? "visit_limit"
                : (remain <= offset ? "frontier_exhausted" : "other"))
            << "\\n";
    // Emit in one write at end of the query; multi-worker output order may vary.
    std::cerr << r47_log.str();
  }
  return std::make_pair(std::make_pair(parlay::to_sequence(frontier),
                                       parlay::to_sequence(visited)),
                        full_dist_cmps);
}''', 'termination')
    return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--input', required=True, type=Path,
                    help='beamSearch.h inside experiments/H47/ copied repository')
    ap.add_argument('--manifest', required=True, type=Path)
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()
    if not args.input.is_file():
        ap.error('input header does not exist')
    if '/experiments/H47/' not in str(args.input.resolve()):
        ap.error('safety: will only patch a copy inside experiments/H47/')
    data = json.loads(args.manifest.read_text())
    qids = sorted(set(data['native_fail_query_ids']))
    if len(qids) != 17:
        ap.error(f'Expected 17 queries, got {len(qids)}')
    old = args.input.read_text()
    new = patch(old, qids)
    if not args.dry_run:
        backup = args.input.with_name(args.input.name + '.r47-original')
        if backup.exists():
            ap.error('backup already exists; refusing to overwrite')
        backup.write_text(old)
        args.input.write_text(new)
    print('R47_PATCH_DRY_RUN_PASS' if args.dry_run else 'R47_PATCH_CREATED_NOT_YET_COMPILED')
    print('target_query_ids=', qids)
    print('markers=', new.count('R47_'))
    print('header=', args.input)


if __name__ == '__main__':
    main()
