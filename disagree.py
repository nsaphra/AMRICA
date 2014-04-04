"""
Author: Naomi Saphra (nsaphra@jhu.edu)

A tool for inspecting AMR data to id patterns of inter-annotator disagreement.
"""

import argparse
import networkx as nx
from amr_metadata import AmrMeta
from smatch import smatch
from collections import defaultdict
import pygraphviz as pgz
import matplotlib.pyplot as plt

def amr_to_graph(inst, rel1, rel2, match=None):
  G = nx.DiGraph()
  for (ind, i) in enumerate(inst):
    if match != None and match[ind] < 0:
      G.add_node(i[1], label='instance=%s' %i[2], color='red')
    else:
      G.add_node(i[1], label='instance=%s' % i[2])

  for r in rel1:
    G.add_node(r[2])
    G.add_edge(r[1], r[2], label=r[0])

  for r in rel2:
    G.add_edge(r[1], r[2], label=r[0])
  return G

def get_amr_line(infile):
  """ Read an entry from the input file. AMRs are separated by blank lines. """
  cur_comments = []
  cur_amr = []
  has_content = False
  for line in infile:
    if line[0] == "(" and len(cur_amr) != 0:
      cur_amr = []
    if line.strip() == "":
      if not has_content:
        continue
      else:
        break
    elif line.strip().startswith("#"):
      cur_comments.append(line.strip())
    else:
      has_content = True
      cur_amr.append(line.strip())
  return ("".join(cur_amr), cur_comments)

def hilight_disagreement(amrs):
  amr_graphs = []
  it = iter(amrs)

  gold_amr = next(it)
  gold_label="b"
  gold_amr.rename_node(gold_label)
  (gold_inst, gold_rel1, gold_rel2) = gold_amr.get_triples2()
  amr_graphs.append(amr_to_graph(gold_inst, gold_rel1, gold_rel2))

  for a in it:
    test_label="a"
    a.rename_node(test_label)
    (test_inst, test_rel1, test_rel2) = a.get_triples2()
    (best_match, best_match_num) = smatch.get_fh(test_inst, test_rel1, test_rel2,
      gold_inst, gold_rel1, gold_rel2,
      test_label, gold_label)

    amr_graphs.append(amr_to_graph(test_inst, test_rel1, test_rel2, best_match))
  return amr_graphs


def main():  
  parser = argparse.ArgumentParser(description='Generate a .dot file to '
    'easy inspection of AMR data for inter-annotator disagreement.')
  parser.add_argument('-i', '--infile',
    default='../data/LDC2013E117/deft-amr-release-r3-events37.txt',
    help='amr input file')
  parser.add_argument('-o', '--outdir',
    default='../data/LDC2013E117/interannotator/deft-amr-release-r3-events37',
    help='.dot output directory')
  args = parser.parse_args()

  infile = open(args.infile)

  amrs_same_sent = []
  cur_id = ""
  while True:
    (amr_line, comments) = get_amr_line(infile)
    if amr_line == "":
      break
    cur_amr = AmrMeta.from_parse(amr_line, comments)

    if 'id' not in cur_amr.metadata:
      print "OH NO THERE IS NO ID"
      continue

    if not cur_id:
      cur_id = cur_amr.metadata['id']

    if cur_id != cur_amr.metadata['id']:
      amr_graphs = hilight_disagreement(amrs_same_sent)
      # TODO  print amr graphs
      for (a, g) in zip(amrs_same_sent, amr_graphs):
        vizG = nx.to_agraph(g)
        vizG.layout(prog='dot')
        vizG.draw('%s/%s_%s.png' % (args.outdir, cur_id, a.metadata['annotator']))
      print("ID: %s\n Sentence: %s" % (cur_id, amrs_same_sent[0].metadata['snt']))
      raw_input("Press enter to continue: ")

      amrs_same_sent = []
      cur_id = cur_amr.metadata['id']

    amrs_same_sent.append(cur_amr)

  infile.close()


if __name__ == '__main__':
  main()