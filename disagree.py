"""
Author: Naomi Saphra (nsaphra@jhu.edu)

A tool for inspecting AMR data to id patterns of inter-annotator disagreement.
"""
# TODO deal with constant name dupes
# TODO TOP for different-instance-names nodes should have same edge
# TODO stats: edges in diff dir?
# TODO stats: diff edge names?
# TODO stats: diff node instance names
# TODO stats: alt edge crosses node?
import argparse
import networkx as nx
from amr_metadata import AmrMeta
from smatch import smatch
from collections import defaultdict
import pygraphviz as pgz
import copy

GOLD_COLOR = 'blue'
TEST_COLOR = 'red'
DFLT_COLOR = 'black'


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


def amr_info_to_dict(inst, rel1, rel2):
  """ Get tables of AMR data indexed by variable number """
  node_inds = {}
  inst_t = {}
  for (ind, (i, v, label)) in enumerate(inst):
    node_inds[v] = ind
    inst_t[ind] = label

  #TODO are multiple edges between two vars allowed?
  rel1_t = {}
  for (label, v1, const) in rel1:
    if (node_inds[v1], const) not in rel1_t:
      rel1_t[(node_inds[v1], const)] = set()
    rel1_t[(node_inds[v1], const)].add(label)

  rel2_t = {}
  for (label, v1, v2) in rel2:
    if (node_inds[v1], node_inds[v2]) not in rel2_t:
      rel2_t[(node_inds[v1], node_inds[v2])] = set()
    rel2_t[(node_inds[v1], node_inds[v2])].add(label)

  return (inst_t, rel1_t, rel2_t)


def amr_disagree_to_graph(inst, rel1, rel2, gold_inst_t, gold_rel1_t, gold_rel2_t, match):
  """ 
  Graph of test AMR / gold AMR union, with hilighted disagreements for 
  different labels on edges and nodes, unmatched nodes and edges.
  Input:
    (inst, rel1, rel2) from test amr.get_triples2()
    (gold_inst_t, gold_rel1_t, gold_rel2_t) from gold amr_info_to_dict()
  """
  G = nx.MultiDiGraph()
  gold_ind = {} # test variable name -> gold variable index
  tablecopy = lambda x: copy.deepcopy(x) #{k:copy.copy(v) for (k,v) in x.items()}
  unmatched_gold_inst = tablecopy(gold_inst_t)
  unmatched_gold_rel1 = tablecopy(gold_rel1_t)
  unmatched_gold_rel2 = tablecopy(gold_rel2_t)

  for (ind, (i, v, instof)) in enumerate(inst):
    gold_ind[v] = match[ind]

    node_color = DFLT_COLOR
    font_color = DFLT_COLOR
    label = instof
    if match[ind] < 0:
      font_color = TEST_COLOR
      node_color = TEST_COLOR
    else:
      if gold_inst_t[match[ind]] != instof:
        font_color = TEST_COLOR
        label = "%s (%s)" % (instof, gold_inst_t[match[ind]])
      if match[ind] in unmatched_gold_inst:
        del unmatched_gold_inst[match[ind]]
    G.add_node(v, label=label, color=node_color, font_color=font_color)

  for (reln, v, const) in rel1:
    node_color = DFLT_COLOR
    edge_color = DFLT_COLOR
    if (gold_ind[v], const) in gold_rel1_t:
      if reln not in gold_rel1_t[(gold_ind[v], const)]:
        edge_color = TEST_COLOR

        # relns between existing nodes should be in unmatched rel2
        gold_ind[const] = const
        unmatched_gold_rel2[(gold_ind[v], const)] = unmatched_gold_rel1[(gold_ind[v], const)]
        del unmatched_gold_rel1[(gold_ind[v], const)]
      else:
        unmatched_gold_rel1[(gold_ind[v], const)].remove(reln)
    else:
      node_color = TEST_COLOR
      edge_color = TEST_COLOR
    # special case: "TOP" specifier not annotated
    if reln == 'TOP':
      G.add_edge(v, v, label=reln, color=edge_color, font_color=edge_color)
      continue
    G.add_node(const, label=const, color=node_color, font_color=node_color)
    G.add_edge(v, const, label=reln, color=edge_color, font_color=edge_color)

  for (reln, v1, v2) in rel2:
    edge_color = DFLT_COLOR
    if (gold_ind[v1], gold_ind[v2]) in gold_rel2_t:
      if reln not in gold_rel2_t[(gold_ind[v1], gold_ind[v2])]:
        edge_color = TEST_COLOR
      else:
        unmatched_gold_rel2[(gold_ind[v1], gold_ind[v2])].remove(reln)
    else:
      edge_color = TEST_COLOR
    G.add_edge(v1, v2, label=reln, color=edge_color, font_color=edge_color)

  # Add gold standard elements not in test
  node_hashes = {v:k for (k,v) in gold_ind.items()} # reverse lookup from gold ind
  for (gold_ind, instof) in unmatched_gold_inst.items():
    node_hashes[gold_ind] = 'GOLD %s' % gold_ind
    G.add_node(node_hashes[gold_ind], label=instof, color=GOLD_COLOR, font_color=GOLD_COLOR)
  for ((gold_ind, const), relns) in unmatched_gold_rel1.items():
    #TODO check if const node already in
    for reln in relns:
      # special case: "TOP" specifier not annotated
      if reln == 'TOP':
        G.add_edge(node_hashes[gold_ind], node_hashes[gold_ind], label=reln, color=GOLD_COLOR, font_color=GOLD_COLOR)
        continue
        
      if const not in node_hashes:
        node_hashes[const] = 'GOLD %s' % const
        G.add_node(const, label=const, color=GOLD_COLOR, font_color=GOLD_COLOR)
      G.add_edge(node_hashes[gold_ind], const, label=reln, color=GOLD_COLOR, font_color=GOLD_COLOR)
  for ((gold_ind1, gold_ind2), relns) in unmatched_gold_rel2.items():
    for reln in relns:
      G.add_edge(node_hashes[gold_ind1], node_hashes[gold_ind2], label=reln, color=GOLD_COLOR, font_color=GOLD_COLOR)
  return G


def hilight_disagreement(gold_amr, test_amrs):
  amr_graphs = []
  gold_label="b"
  gold_amr.rename_node(gold_label)
  (gold_inst, gold_rel1, gold_rel2) = gold_amr.get_triples2()
  (gold_inst_t, gold_rel1_t, gold_rel2_t) = amr_info_to_dict(gold_inst, gold_rel1, gold_rel2)

  for a in test_amrs:
    test_label="a"
    a.rename_node(test_label)
    (test_inst, test_rel1, test_rel2) = a.get_triples2()
    (best_match, best_match_num) = smatch.get_fh(test_inst, test_rel1, test_rel2,
      gold_inst, gold_rel1, gold_rel2,
      test_label, gold_label)

    amr_graphs.append(amr_disagree_to_graph(test_inst, test_rel1, test_rel2, gold_inst_t, gold_rel1_t, gold_rel2_t, best_match))
  return amr_graphs


def edge_agrees(e):
  # TODO handle instance label disagreement
  return e['color'] == DFLT_COLOR


def disagree_stats_edges(g):
  total_edges = len(g.edges())
  total_disagree = 0
  disagree_labels = defaultdict(int)
  for (v1, v2, dat) in g.edges(data=True):
    if edge_agrees(dat):
      continue
    total_disagree += 1
    disagree_labels[dat['label']] += 1





def main():
  parser = argparse.ArgumentParser(description='Generate a .dot file to '
    'easy inspection of AMR data for inter-annotator disagreement.')
  parser.add_argument('-i', '--infile',
    default='../data/LDC2013E117/deft-amr-release-r3-events37.txt',
    help='amr input file')
  parser.add_argument('-o', '--outdir',
    default='../data/LDC2013E117/interannotator/deft-amr-release-r3-events37',
    help='image output directory')
  args = parser.parse_args()

  infile = open(args.infile)
  amrs_same_sent = []
  cur_id = ""
  while True:
    (amr_line, comments) = get_amr_line(infile)
    if amr_line == "":
      break
    cur_amr = AmrMeta.from_parse(amr_line, comments)
    assert 'id' in cur_amr.metadata and 'annotator' in cur_amr.metadata
    if not cur_id:
      cur_id = cur_amr.metadata['id']

    if cur_id != cur_amr.metadata['id']:
      gold_amr = amrs_same_sent[0]
      test_amrs = amrs_same_sent[1:]
      amr_graphs = hilight_disagreement(gold_amr, test_amrs)

      gold_anno = gold_amr.metadata['annotator']
      sent = gold_amr.metadata['snt']

      for (a, g) in zip(test_amrs, amr_graphs):
        test_anno = a.metadata['annotator']

        disagree_stats_edges(g)

        ag = nx.to_agraph(g)
        ag.layout(prog='dot')
        ag.draw('%s/%s_annoted_%s_%s.png' % (args.outdir, cur_id, gold_anno, test_anno))

      print("ID: %s\n Sentence: %s" % (cur_id, sent))
      #raw_input("Press enter to continue: ")

      amrs_same_sent = []
      cur_id = cur_amr.metadata['id']

    amrs_same_sent.append(cur_amr)

  infile.close()


if __name__ == '__main__':
  main()