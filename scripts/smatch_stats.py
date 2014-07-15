#!/usr/bin/env python

import argparse
from collections import defaultdict
from networkx.readwrite import json_graph
import sys

from compare_smatch.smatch_graph import SmatchGraph

sys.path.append("..")

counts = defaultdict(int)

def add_counts(g, v1, v2, attr, prefix):
  def pfx(lbl):
    return '%s_%s' % (prefix, lbl)
  def opp(lbl):
    if prefix == 'gold':
      return 'test_%s' % lbl
    if prefix == 'test':
      return 'gold_%s' % lbl
    else:
      raise Exception #TODO think of a good exception
  def incr(lbl):
    counts['total_%s' % lbl] += 1
    counts[pfx(lbl)] += 1
  def is_dflt(curr_attr):
    return curr_attr['gold_label'] == curr_attr['test_label']
  def is_opp(curr_attr):
    return curr_attr['color'] != attr['color'] and not is_dflt(curr_attr)
  def is_same(curr_attr):
    return curr_attr['color'] == attr['color']

  incr('edges')
  if attr['label'] == 'polarity':
    incr('polarity')
  if attr['label'].startswith('op') and len(attr['label']) == 3:
    incr('name_opt')
    return
  if g.node[v2]['color'] == attr['color']:
    incr('same_color_head')
  if g.node[v1]['color'] == attr['color']:
    incr('same_color_tail')
  if prefix != 'dflt':
    for head, edges in g.edge[v1].items():
      for (ind, curr) in edges.items():
        if is_same(curr):
          continue
        if head == v2:
          if is_opp(curr):
            incr('cfg1')
        else:
          for head2, edges2 in g.edge[v1].items():
            for (ind2, curr2) in edges2.items():
              if head2 == v2 and is_opp(curr2):
                if is_dflt(curr):
                  incr('cfg2')
                else: # is_opp
                  incr('cfg3')

    for head, edges in g.edge[v2].items():
      for (ind, attrs) in edges.items():
        if head == v1:
          if is_opp(curr):
            incr('cfg1_reverse')


def analyze(g):
  for (v1, links) in g.adjacency_iter():
    for (v2, edges) in links.items():
      for (ind, attr) in edges.items():
        if not attr['gold_label']:
          add_counts(g, v1, v2, attr, 'test')
        elif not attr['test_label']:
          add_counts(g, v1, v2, attr, 'gold')
        else:
          add_counts(g, v1, v2, attr, 'dflt')


def print_proportions():
  for k,v in sorted(counts.items()):
    if k != 'total_edges':
      print '%s: %f' % (k,v/float(counts['total_edges']))

def main(args):
  input_fh = open(args.input)
  while True:
    line = input_fh.readline().strip()
    if not line:
      break
    g = json_graph.loads(line)
    analyze(g)
  input_fh.close()
  for k,v in sorted(counts.items()):
    print '%s: %d' % (k,v)
  print '======='
  print_proportions()


if __name__ == '__main__':
  parser = argparse.ArgumentParser(
    description='Statistical analysis of smatch disagreement graphs.\n'
    'Usage: ./smatch_stats.py -i graphs.json'
  )
  parser.add_argument('-i', '--input',
    help='Specify .json amr disagreement file')
  args = parser.parse_args()

  main(args)