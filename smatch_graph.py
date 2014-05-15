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

class SmatchGraph:
  def __init__(self, inst, rel1, rel2, \
    gold_inst, gold_rel1, gold_rel2, \
    match, const_map_fn=default_aligner.const_map_fn, prebuilt_tables=False):
    """
    Input:
      (inst, rel1, rel2) from test amr.get_triples2()
      (gold_inst, gold_rel1, gold_rel2) from gold amr.get_triples2()
      match from smatch
      const_map_fn picks the matched gold label for a test label
      prebuilt_tables if (gold_inst, gold_rel1, gold_rel2) from gold amr2dict()
    """
    (self.inst, self.rel1, self.rel2) = (inst, rel1, rel2)
    if prebuilt_tables:
      (self.gold_inst_t, self.gold_rel1_t, self.gold_rel2_t) = \
        (gold_inst, gold_rel1, gold_rel2)
    else:
      (self.gold_inst_t, self.gold_rel1_t, self.gold_rel2_t) = \
        amr2dict(gold_inst, gold_rel1, gold_rel2)
    self.match = match
    self.map_fn = const_map_fn

    (self.unmatched_inst, self.unmatched_rel1, self.unmatched_rel2) = \
      [copy.deepcopy(x) for x in (self.gold_inst_t, self.gold_rel1_t, self.gold_rel2_t)]
    self.gold_ind = {} # test variable name -> gold variable index
    self.G = nx.MultiDiGraph()

  def smatch2graph(self):
    """
    Returns graph of test AMR / gold AMR union, with hilighted disagreements for
    different labels on edges and nodes, unmatched nodes and edges.
    """

    for (ind, (i, v, instof)) in enumerate(self.inst):
      self.add_inst(ind, v, instof)

    # TODO decision: color all consts appearing in both charts black OR
    #      have consts hashed according to parent
    # TODO either expand the number of possible const matches
    #      or switch to a word-alignment-variant model
    for (reln, v, const) in self.rel1:
      self.add_rel1(reln, v, const)

    for (reln, v1, v2) in self.rel2:
      self.add_rel2(reln, v1, v2)

    # Add gold standard elements not in test
    node_hashes = {v:k for (k,v) in self.gold_ind.items()} # reverse lookup from gold ind
    for (ind, instof) in self.unmatched_inst.items():
      node_hashes[ind] = 'GOLD %s' % ind
      self.G.add_node(node_hashes[ind], label=instof, color=GOLD_COLOR, font_color=GOLD_COLOR)
    for ((ind, const), relns) in self.unmatched_rel1.items():
      #TODO check if const node already in
      for reln in relns:
        # special case: "TOP" specifier not annotated
        if reln == 'TOP':
          self.G.add_edge(node_hashes[ind], node_hashes[ind], label=reln, color=GOLD_COLOR, font_color=GOLD_COLOR)
          continue

        const_hash = node_hashes[ind] + ' ' + const
        if const_hash not in node_hashes:
          node_hashes[const_hash] = const_hash
          self.G.add_node(const_hash, label=const, color=GOLD_COLOR, font_color=GOLD_COLOR)
        self.G.add_edge(node_hashes[ind], node_hashes[const_hash], label=reln, color=GOLD_COLOR, font_color=GOLD_COLOR)
    for ((ind1, ind2), relns) in self.unmatched_rel2.items():
      for reln in relns:
        self.G.add_edge(node_hashes[ind1], node_hashes[ind2], label=reln, color=GOLD_COLOR, font_color=GOLD_COLOR)
    return self.G

  def add_edge(self, v1, v2, test_lbl, gold_lbl):
    assert(gold_lbl == '' or test_lbl == '' or gold_lbl == test_lbl)
    if gold_lbl == '':
      self.G.add_edge(v1, v2, label=test_lbl, test_label=test_lbl, color=TEST_COLOR)
    elif test_lbl == '':
      self.G.add_edge(v1, v2, label=gold_lbl, gold_label=gold_lbl, color=GOLD_COLOR)
    elif test_lbl == gold_lbl:
      self.G.add_edge(v1, v2, label=test_lbl, test_label=test_lbl, gold_label=gold_lbl, color=DFLT_COLOR)

  def add_node(self, v, test_lbl, gold_lbl):
    assert(gold_lbl or test_lbl)
    if gold_lbl == '':
      self.G.add_node(v, label=test_lbl, test_label=test_lbl, color=TEST_COLOR)
    elif test_lbl == '':
      self.G.add_node(v, label=gold_lbl, gold_label=gold_lbl, color=GOLD_COLOR)
    elif test_lbl == gold_lbl:
      self.G.add_node(v, label=test_lbl, test_label=test_lbl, gold_label=gold_lbl, color=DFLT_COLOR)
    else:
      self.G.add_node(v, label="%s (%s)" % (test_lbl, gold_lbl), test_label=test_lbl, gold_label=gold_lbl, color=DFLT_COLOR)

  def add_inst(self, ind, var, instof):
    self.gold_ind[var] = self.match[ind]
    gold_lbl = ''
    if self.match[ind] >= 0: # there's a gold match
      gold_lbl = self.gold_inst_t[self.match[ind]]
      if self.match[ind] in self.unmatched_inst:
        del self.unmatched_inst[self.match[ind]]
    self.add_node(var, instof, gold_lbl)

  def add_rel1(self, reln, var, const):
    const_match = self.map_fn(const)
    gold_edge_lbl = ''

    # special case: "TOP" specifier not annotated
    if reln == 'TOP':
      # find similar TOP edges in gold if they are not labeled with same instance
      if reln in self.gold_rel1_t.get((self.gold_ind[var], const_match), {}):
        for ((v_, c_), r_) in self.unmatched_rel1.items():
          if v_ == self.gold_ind[var] and 'TOP' in r_:
            gold_edge_lbl = reln
            self.unmatched_rel1[(v_, c_)].remove('TOP')
            break
      self.add_edge(var, var, reln, gold_edge_lbl)
      return

    gold_node_lbl = ''
    node_hash = var+' '+const,
    if (self.gold_ind[var], const_match) in self.gold_rel1_t:
      gold_node_lbl = const_match
      #TODO put the metatable editing in the helper fcns?
      if reln not in self.gold_rel1_t[(self.gold_ind[var], const_match)]:
        # relns between existing nodes should be in unmatched rel2
        self.gold_ind[node_hash] = const_match
        self.unmatched_rel2[(self.gold_ind[var], const_match)] = self.unmatched_rel1[(self.gold_ind[var], const_match)]
        del self.unmatched_rel1[(self.gold_ind[var], const_match)]
      else:
        gold_edge_lbl = reln
        self.unmatched_rel1[(self.gold_ind[var], const_match)].remove(reln)

    self.add_node(node_hash, const, gold_node_lbl)
    self.add_edge(var, node_hash, reln, gold_edge_lbl)

  def add_rel2(self, reln, v1, v2):
    gold_lbl = ''
    if (self.gold_ind[v1], self.gold_ind[v2]) in self.gold_rel2_t:
      if reln in self.gold_rel2_t[(self.gold_ind[v1], self.gold_ind[v2])]:
        gold_lbl = reln
        self.unmatched_rel2[(self.gold_ind[v1], self.gold_ind[v2])].remove(reln)
    self.add_edge(v1, v2, reln, gold_lbl)


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