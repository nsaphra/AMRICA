#!/usr/bin/env python
"""
Author: Naomi Saphra (nsaphra@jhu.edu)

Describes a class for building graphs of AMRs with disagreements hilighted.
"""

# TODO deal with constant name dupes
import networkx as nx
import amr_metadata
from amr_alignment import Amr2AmrAligner
from amr_alignment import default_aligner
from smatch import smatch
from collections import defaultdict
import pygraphviz as pgz
import copy
import ConfigParser
from pynlpl.formats.giza import GizaSentenceAlignment

GOLD_COLOR = 'blue'
TEST_COLOR = 'red'
DFLT_COLOR = 'black'

def amr2dict(inst, rel1, rel2):
  """ Get tables of AMR data indexed by variable number """
  node_inds = {}
  inst_t = {}
  for (ind, (i, v, label)) in enumerate(inst):
    node_inds[v] = ind
    inst_t[ind] = label

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


def smatch2graph(inst, rel1, rel2, gold_inst_t, gold_rel1_t, gold_rel2_t, match, const_map_fn):
  """ 
  Input:
    (inst, rel1, rel2) from test amr.get_triples2()
    (gold_inst_t, gold_rel1_t, gold_rel2_t) from gold amr_info_to_dict()
  Returns graph of test AMR / gold AMR union, with hilighted disagreements for
  different labels on edges and nodes, unmatched nodes and edges.
  """

  G = nx.MultiDiGraph()
  gold_ind = {} # test variable name -> gold variable index
  tablecopy = lambda x: copy.deepcopy(x)
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

  # TODO decision: color all consts appearing in both charts black OR
  #      have consts hashed according to parent
  # TODO either expand the number of possible const matches
  #      or switch to a word-alignment-variant model
  for (reln, v, const) in rel1:
    node_color = DFLT_COLOR
    edge_color = DFLT_COLOR
    label = const
    const_match = const_map_fn(const)
    if (gold_ind[v], const_match) in gold_rel1_t:
      if const != const_match:
        label = "%s (%s)" % (const, const_match)
      if reln not in gold_rel1_t[(gold_ind[v], const_match)]:
        edge_color = TEST_COLOR

        # relns between existing nodes should be in unmatched rel2
        gold_ind[const] = const_match
        unmatched_gold_rel2[(gold_ind[v], const_match)] = unmatched_gold_rel1[(gold_ind[v], const_match)]
        del unmatched_gold_rel1[(gold_ind[v], const_match)]
      else:
        unmatched_gold_rel1[(gold_ind[v], const_match)].remove(reln)
    else:
      node_color = TEST_COLOR
      edge_color = TEST_COLOR
    # special case: "TOP" specifier not annotated
    if reln == 'TOP':
      # find similar TOP edges in gold if they are not labeled with same instance
      if edge_color == TEST_COLOR:
        for ((v_, c_), r_) in unmatched_gold_rel1.items():
          if v_ == gold_ind[v] and 'TOP' in r_:
            edge_color = DFLT_COLOR
            unmatched_gold_rel1[(v_, c_)].remove('TOP')
      G.add_edge(v, v, label=reln, color=edge_color, font_color=edge_color)
      continue
    G.add_node(v+' '+const, label=label, color=node_color, font_color=node_color)
    G.add_edge(v, v+' '+const, label=reln, color=edge_color, font_color=edge_color)

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

      const_hash = node_hashes[gold_ind] + ' ' + const
      if const_hash not in node_hashes:
        node_hashes[const_hash] = const_hash
        G.add_node(const_hash, label=const, color=GOLD_COLOR, font_color=GOLD_COLOR)
      G.add_edge(node_hashes[gold_ind], node_hashes[const_hash], label=reln, color=GOLD_COLOR, font_color=GOLD_COLOR)
  for ((gold_ind1, gold_ind2), relns) in unmatched_gold_rel2.items():
    for reln in relns:
      G.add_edge(node_hashes[gold_ind1], node_hashes[gold_ind2], label=reln, color=GOLD_COLOR, font_color=GOLD_COLOR)
  return G

