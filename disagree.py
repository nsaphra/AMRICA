#!/usr/bin/env python
"""
Author: Naomi Saphra (nsaphra@jhu.edu)

A tool for inspecting AMR data to id patterns of inter-annotator disagreement
or semantic inequivalence.

AMR input file expected in format where comments above each annotation indicate
the sentence like so:

# ::id DF-170-181103-888_2097.1 ::date 2013-09-16T07:15:31 ::annotator ANON-01 ::preferred
# ::snt This is a sentence.

For monolingual disagreement, all annotations of some sentence should occur
consecutively in the monolingual annotation file. For bilingual, annotations
should be in the same order of sentences between the files.
"""

# TODO deal with constant name dupes
# TODO TOP for different-instance-names nodes should have same edge
# TODO multiline sentences don't print right
import argparse
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
from pynlpl.common import u
import codecs

GOLD_COLOR = 'blue'
TEST_COLOR = 'red'
DFLT_COLOR = 'black'

def amr_info_to_dict(inst, rel1, rel2):
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


def amr_disagree_to_graph(inst, rel1, rel2, gold_inst_t, gold_rel1_t, gold_rel2_t, match):
  """ 
  Input:
    (inst, rel1, rel2) from test amr.get_triples2()
    (gold_inst_t, gold_rel1_t, gold_rel2_t) from gold amr_info_to_dict()
  Returns graph of test AMR / gold AMR union, with hilighted disagreements for
  different labels on edges and nodes, unmatched nodes and edges.
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


def hilight_disagreement(test_amrs, gold_amr, aligner=default_aligner):
  """
  Input:
    gold_amr: gold AMR object
    test_amrs: list of AMRs to compare to
  Returns list of disagreement graphs for each gold-test AMR pair.
  """

  amr_graphs = []
  gold_label="b"
  gold_amr.rename_node(gold_label)
  (gold_inst, gold_rel1, gold_rel2) = gold_amr.get_triples2()
  (gold_inst_t, gold_rel1_t, gold_rel2_t) = amr_info_to_dict(gold_inst, gold_rel1, gold_rel2)

  for a in test_amrs:
    aligner.set_amrs(a, gold_amr)
    test_label="a"
    a.rename_node(test_label)
    (test_inst, test_rel1, test_rel2) = a.get_triples2()
    (best_match, best_match_num) = smatch.get_fh(test_inst, test_rel1, test_rel2,
      gold_inst, gold_rel1, gold_rel2,
      test_label, gold_label, const_weight_fn=aligner.weight_fn, instance_weight_fn=aligner.weight_fn)

    amr_graphs.append(amr_disagree_to_graph(test_inst, test_rel1, test_rel2, gold_inst_t, gold_rel1_t, gold_rel2_t, best_match))
  return amr_graphs


def monolingual_main(args):
  infile = codecs.open(args.infile, encoding='utf8')
  amrs_same_sent = []
  cur_id = ""
  # TODO single-amr representation
  while True:
    (amr_line, comments) = amr_metadata.get_amr_line(infile)
    if amr_line == "":
      break
    cur_amr = amr_metadata.AmrMeta.from_parse(amr_line, comments)
    assert 'id' in cur_amr.metadata and 'annotator' in cur_amr.metadata
    if not cur_id:
      cur_id = cur_amr.metadata['id']

    if cur_id != cur_amr.metadata['id']:
      gold_amr = amrs_same_sent[0]
      test_amrs = amrs_same_sent[1:]
      amr_graphs = hilight_disagreement(test_amrs, gold_amr)

      gold_anno = gold_amr.metadata['annotator']
      sent = gold_amr.metadata['snt']

      for (a, g) in zip(test_amrs, amr_graphs):
        test_anno = a.metadata['annotator']
        
        ag = nx.to_agraph(g)
        ag.layout(prog='dot')
        ag.draw('%s/%s_annoted_%s_%s.png' % (args.outdir, cur_id, gold_anno, test_anno))

      if (args.verbose):
        print("ID: %s\n Sentence: %s" % (cur_id, sent))
      #raw_input("Press enter to continue: ")

      amrs_same_sent = []
      cur_id = cur_amr.metadata['id']

    amrs_same_sent.append(cur_amr)

  infile.close()


def xlang_main(args):
  src_amr_fh = codecs.open(args.src_amr, encoding='utf8')
  tgt_amr_fh = codecs.open(args.tgt_amr, encoding='utf8')
  src2tgt_fh = codecs.open(args.align_src2tgt, encoding='utf8')
  tgt2src_fh = codecs.open(args.align_tgt2src, encoding='utf8')
  tgt_align_fh = codecs.open(args.align_tgtamr2snt, encoding='utf8')

  amrs_same_sent = []
  aligner = Amr2AmrAligner(num_best=int(args.num_align), src2tgt_fh=src2tgt_fh, tgt2src_fh=tgt2src_fh, tgt_align_fh=tgt_align_fh)
  while True:
    (src_amr_line, src_comments) = amr_metadata.get_amr_line(src_amr_fh)
    if src_amr_line == "":
      break
    (tgt_amr_line, tgt_comments) = amr_metadata.get_amr_line(tgt_amr_fh)
    src_amr = amr_metadata.AmrMeta.from_parse(src_amr_line, src_comments)
    tgt_amr = amr_metadata.AmrMeta.from_parse(tgt_amr_line, tgt_comments)
    assert src_amr.metadata['id'] == tgt_amr.metadata['id']
    cur_id = src_amr.metadata['id']

    src_sent = src_amr.metadata['snt']
    tgt_sent = tgt_amr.metadata['snt']

    # TODO make this more modular, beyond zh-en
    amr_graphs = hilight_disagreement([tgt_amr], src_amr, aligner=aligner)
    ag = nx.to_agraph(amr_graphs[0])
    ag.layout(prog='dot')
    ag.draw('%s/%s.png' % (args.outdir, cur_id))

    if (args.verbose):
      print("ID: %s\n Sentence: %s" % (cur_id, src_sent))
    #raw_input("Press enter to continue: ")

  src_amr_fh.close()
  tgt_amr_fh.close()
  src2tgt_fh.close()
  tgt2src_fh.close()


if __name__ == '__main__':
  conf_parser = argparse.ArgumentParser(add_help=False)
  conf_parser.add_argument("-c", "--conf_file",
    help="Specify config file", metavar="FILE")
  args, remaining_argv = conf_parser.parse_known_args()
  defaults = {}
  if args.conf_file:
    config = ConfigParser.SafeConfigParser()
    config.read([args.conf_file])
    defaults = dict(config.items("Defaults"))

  parser = argparse.ArgumentParser(
    parents=[conf_parser],
    description='Generate graphviz png files for '
    'easy inspection of AMR data for inter-annotator disagreement.\n'
    'Usage: ./disagree.py -i all_amrs.txt -o png_dir/\n'
    '(Or specify config file with -c)',
    formatter_class=argparse.RawDescriptionHelpFormatter,
  )
  parser.set_defaults(**defaults)
  parser.add_argument('-i', '--infile', help='amr input file')
  parser.add_argument('-o', '--outdir', help='image output directory')
  parser.add_argument('-v', '--verbose', action='store_true')
  parser.add_argument('-b', '--bitext', action='store_true',
    help='Input source and target language bitext AMRs.')
  parser.add_argument('-s', '--src_amr',
    help='In bitext mode, source language AMR file.')
  parser.add_argument('-t', '--tgt_amr',
    help='In bitext mode, target language AMR file.')
  parser.add_argument('--align_src2tgt',
    help='In bitext mode, GIZA alignment .NBEST file (see GIZA++ -nbestalignments opt) with source as vcb1.')
  parser.add_argument('--align_tgt2src',
    help='In bitext mode, GIZA alignment .NBEST file (see GIZA++ -nbestalignments opt) with target as vcb1.')
  parser.add_argument('--align_tgtamr2snt',
    help='In bitext mode, file aligning target AMR to sentence tokens.')
  parser.add_argument('--num_align',
    help='N for GIZA NBEST file.')
  # TODO make interactive option and option to process a specific range
  args = parser.parse_args(remaining_argv)

  if (args.bitext):
    xlang_main(args)
  else:
    monolingual_main(args)