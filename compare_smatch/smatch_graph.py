#!/usr/bin/env python
"""
smatch_graph.py

Author: Naomi Saphra (nsaphra@jhu.edu)
Copyright(c) 2014

Describes a class for building graphs of AMRs with disagreements hilighted.
"""

import copy
import networkx as nx
import pygraphviz as pgz
from pynlpl.formats.giza import GizaSentenceAlignment

from amr_alignment import Amr2AmrAligner
from amr_alignment import default_aligner
import amr_metadata
from smatch import smatch

GOLD_COLOR = 'blue'
TEST_COLOR = 'red'
DFLT_COLOR = 'black'

class SmatchGraph:
  def __init__(self, inst, rel1, rel2, \
    gold_inst_t, gold_rel1_t, gold_rel2_t, \
    match, const_map_fn=default_aligner.const_map_fn):
    """
    TODO correct these params
    Input:
      (inst, rel1, rel2) from test amr.get_triples2()
      (gold_inst_t, gold_rel1_t, gold_rel2_t) from gold amr2dict()
      match from smatch
      const_map_fn returns a sorted list of gold label matches for a test label
    """
    (self.inst, self.rel1, self.rel2) = (inst, rel1, rel2)
    (self.gold_inst_t, self.gold_rel1_t, self.gold_rel2_t) = \
      (gold_inst_t, gold_rel1_t, gold_rel2_t)
    self.match = match # test var index -> gold var index
    self.map_fn = const_map_fn

    (self.unmatched_inst, self.unmatched_rel1, self.unmatched_rel2) = \
      [copy.deepcopy(x) for x in (self.gold_inst_t, self.gold_rel1_t, self.gold_rel2_t)]
    self.gold_ind = {} # test variable hash -> gold variable index
    self.G = nx.MultiDiGraph()

  def smatch2graph(self, node_weight_fn=None, edge_weight_fn=None):
    """
    Returns graph of test AMR / gold AMR union, with hilighted disagreements for
    different labels on edges and nodes, unmatched nodes and edges.
    """

    for (ind, (i, v, instof)) in enumerate(self.inst):
      self.add_inst(ind, v, instof)

    for (reln, v, const) in self.rel1:
      self.add_rel1(reln, v, const)

    for (reln, v1, v2) in self.rel2:
      self.add_rel2(reln, v1, v2)

    if node_weight_fn and edge_weight_fn:
      self.unmatch_dead_nodes(node_weight_fn, edge_weight_fn)

    # Add gold standard elements not in test
    test_ind = {v:k for (k,v) in self.gold_ind.items()} # reverse lookup from gold ind

    for (ind, instof) in self.unmatched_inst.items():
      test_ind[ind] = u'GOLD %s' % ind
      self.add_node(test_ind[ind], '', instof, test_ind=-1, gold_ind=ind)

    for ((ind, const), relns) in self.unmatched_rel1.items():
      for reln in relns:
        const_hash = test_ind[ind] + ' ' + const
        if const_hash not in test_ind:
          test_ind[const_hash] = const_hash
          self.add_node(const_hash, '', const)
        self.add_edge(test_ind[ind], test_ind[const_hash], '', reln)

    for ((ind1, ind2), relns) in self.unmatched_rel2.items():
      for reln in relns:
        self.add_edge(test_ind[ind1], test_ind[ind2], '', reln)

    return self.G

  def get_text_alignments(self):
    """ Return an array of variable ID mappings, including labels, that are human-readable.
        Call only after smatch2graph(). """
    align = []
    for (v, attr) in self.G.nodes(data=True):
      if attr['test_ind'] < 0 and attr['gold_ind'] < 0:
        continue
      align.append("%s\t%s\t-\t%s\t%s" % (attr['test_ind'], attr['test_label'], attr['gold_ind'], attr['gold_label']))
    return align

  def add_edge(self, v1, v2, test_lbl, gold_lbl):
    assert(gold_lbl == '' or test_lbl == '' or gold_lbl == test_lbl)
    if gold_lbl == '':
      self.G.add_edge(v1, v2, label=test_lbl, test_label=test_lbl, gold_label=gold_lbl, color=TEST_COLOR)
    elif test_lbl == '':
      self.G.add_edge(v1, v2, label=gold_lbl, test_label=test_lbl, gold_label=gold_lbl, color=GOLD_COLOR)
    elif test_lbl == gold_lbl:
      self.G.add_edge(v1, v2, label=test_lbl, test_label=test_lbl, gold_label=gold_lbl, color=DFLT_COLOR)

  def add_node(self, v, test_lbl, gold_lbl, test_ind=-1, gold_ind=-1):
    assert(gold_lbl or test_lbl)
    if gold_lbl == '':
      self.G.add_node(v, label=u'%s / *' % test_lbl, test_label=test_lbl, gold_label=gold_lbl, \
        test_ind=test_ind, gold_ind=gold_ind, color=TEST_COLOR)
    elif test_lbl == '':
      self.G.add_node(v, label=u'* / %s' % gold_lbl, test_label=test_lbl, gold_label=gold_lbl, \
        test_ind=test_ind, gold_ind=gold_ind, color=GOLD_COLOR)
    elif test_lbl == gold_lbl:
      self.G.add_node(v, label=test_lbl, test_label=test_lbl, gold_label=gold_lbl, \
        test_ind=test_ind, gold_ind=gold_ind, color=DFLT_COLOR)
    else:
      self.G.add_node(v, label=u'%s / %s' % (test_lbl, gold_lbl), test_label=test_lbl, gold_label=gold_lbl, \
        test_ind=test_ind, gold_ind=gold_ind, color=DFLT_COLOR)

  def add_inst(self, ind, var, instof):
    self.gold_ind[var] = self.match[ind]
    gold_lbl = ''
    gold_ind = self.match[ind]
    if gold_ind >= 0: # there's a gold match
      gold_lbl = self.gold_inst_t[gold_ind]
      if self.match[ind] in self.unmatched_inst:
        del self.unmatched_inst[gold_ind]
    self.add_node(var, instof, gold_lbl, test_ind=ind, gold_ind=gold_ind)

  def add_rel1(self, reln, var, const):
    const_matches = self.map_fn(const)
    gold_edge_lbl = ''

    # we match const to the highest-ranked match label from the var
    gold_node_lbl = ''
    node_hash = var+' '+const
    for const_match in const_matches:
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
        break

    self.add_node(node_hash, const, gold_node_lbl)
    self.add_edge(var, node_hash, reln, gold_edge_lbl)

  def add_rel2(self, reln, v1, v2):
    gold_lbl = ''
    if (self.gold_ind[v1], self.gold_ind[v2]) in self.gold_rel2_t:
      if reln in self.gold_rel2_t[(self.gold_ind[v1], self.gold_ind[v2])]:
        gold_lbl = reln
        self.unmatched_rel2[(self.gold_ind[v1], self.gold_ind[v2])].remove(reln)
    self.add_edge(v1, v2, reln, gold_lbl)

  def unmatch_dead_nodes(self, node_weight_fn, edge_weight_fn):
    """ Unmap node mappings that don't increase smatch score. """
    node_is_live = {v:(gold == -1) for (v, gold) in self.gold_ind.items()}
    for (v, attr) in self.G.nodes(data=True):
      if node_weight_fn(attr['test_label'], attr['gold_label']) > 0:
        node_is_live[v] = True
    for (v1, links) in self.G.adjacency_iter():
      for (v2, edges) in links.items():
        if len(edges) > 1:
          node_is_live[v2] = True
          node_is_live[v1] = True
          break
        for (ind, attr) in edges.items():
          if attr['test_label'] == attr['gold_label']:
            node_is_live[v2] = True
            node_is_live[v1] = True
            break

    for v in node_is_live.keys():
      if not node_is_live[v]:
        self.unmatched_inst[self.gold_ind[v]] = self.G.node[v]['gold_label']
        self.G.node[v]['gold_label'] = ''
        self.G.node[v]['label'] = u'%s / *' % self.G.node[v]['test_label']
        self.G.node[v]['color'] = TEST_COLOR
        del self.gold_ind[v]


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
