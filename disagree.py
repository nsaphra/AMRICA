#!/usr/bin/env python
"""
Author: Naomi Saphra (nsaphra@jhu.edu)

A tool for inspecting AMR data to id patterns of inter-annotator disagreement
or semantic inequivalence.

AMR input file expected in format where comments above each annotation indicate
the sentence like so:

# ::id DF-170-181103-888_2097.1 ::date 2013-09-16T07:15:31 ::annotator ANON-01 ::preferred
# ::tok This is a sentence.

For monolingual disagreement, all annotations of some sentence should occur
consecutively in the monolingual annotation file. For bilingual, annotations
should be in the same order of sentences between the files.
"""

import argparse
import networkx as nx
from networkx.readwrite import json_graph
from compare_smatch.amr_alignment import Amr2AmrAligner
from compare_smatch.amr_alignment import default_aligner
from smatch import smatch
from collections import defaultdict
import pygraphviz as pgz
import copy
import ConfigParser
from pynlpl.formats.giza import GizaSentenceAlignment
import codecs
from compare_smatch import amr_metadata
from compare_smatch import smatch_graph
from compare_smatch.smatch_graph import SmatchGraph
# TODO better config/args system

def hilight_disagreement(test_amrs, gold_amr, aligner=default_aligner):
  """
  Input:
    gold_amr: gold AMR object
    test_amrs: list of AMRs to compare to
  Returns list of disagreement graphs for each gold-test AMR pair.
  """

  amr_graphs = []
  gold_label=u'b'
  gold_amr.rename_node(gold_label)
  (gold_inst, gold_rel1, gold_rel2) = gold_amr.get_triples2()
  (gold_inst_t, gold_rel1_t, gold_rel2_t) = smatch_graph.amr2dict(gold_inst, gold_rel1, gold_rel2)

  for a in test_amrs:
    aligner.set_amrs(a, gold_amr)
    test_label=u'a'
    a.rename_node(test_label)
    (test_inst, test_rel1, test_rel2) = a.get_triples2()
    (best_match, best_match_num) = smatch.get_fh(test_inst, test_rel1, test_rel2,
      gold_inst, gold_rel1, gold_rel2,
      test_label, gold_label, const_weight_fn=aligner.weight_fn, instance_weight_fn=aligner.weight_fn)

    disagreement = SmatchGraph(test_inst, test_rel1, test_rel2, \
      gold_inst_t, gold_rel1_t, gold_rel2_t, \
      best_match, const_map_fn=aligner.const_map_fn, prebuilt_tables=True)
    amr_graphs.append(disagreement.smatch2graph(weight_fn=aligner.weight_fn))
  return amr_graphs


def monolingual_main(args):
  infile = codecs.open(args.infile, encoding='utf8')
  json_fh = None
  if args.json:
    json_fh = codecs.open(args.json, 'w', encoding='utf8')

  amrs_same_sent = []
  cur_id = ""
  while True:
    (amr_line, comments) = amr_metadata.get_amr_line(infile)
    if amr_line == "":
      break
    cur_amr = amr_metadata.AmrMeta.from_parse(amr_line, comments)
    assert 'id' in cur_amr.metadata
    if not cur_id:
      cur_id = cur_amr.metadata['id']
    if 'annotator' not in cur_amr.metadata:
      cur_amr.metadata['annotator'] = ''

    if cur_id != cur_amr.metadata['id']:
      gold_amr = amrs_same_sent[0]
      test_amrs = amrs_same_sent[1:]
      if len(test_amrs) == 0:
        test_amrs = [gold_amr] # single AMR view case
      amr_graphs = hilight_disagreement(test_amrs, gold_amr)

      gold_anno = gold_amr.metadata['annotator']
      sent = gold_amr.metadata['tok']

      for (a, g) in zip(test_amrs, amr_graphs):
        test_anno = a.metadata['annotator']
        if json_fh:
          json_fh.write(json_graph.dumps(g) + '\n')

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
  if json_fh:
    json_fh.close()


def xlang_main(args):
  """ Disagreement graphs for aligned cross-language language. """
  src_amr_fh = codecs.open(args.src_amr, encoding='utf8')
  tgt_amr_fh = codecs.open(args.tgt_amr, encoding='utf8')
  src2tgt_fh = codecs.open(args.align_src2tgt, encoding='utf8')
  tgt2src_fh = codecs.open(args.align_tgt2src, encoding='utf8')
  tgt_align_fh = codecs.open(args.align_tgtamr2snt, encoding='utf8')

  json_fh = None
  if args.json:
    json_fh = codecs.open(args.json, 'w', encoding='utf8')

  amrs_same_sent = []
  aligner = Amr2AmrAligner(num_best=int(args.num_align_read), num_best_in_file=int(args.num_aligned_in_file), src2tgt_fh=src2tgt_fh, tgt2src_fh=tgt2src_fh, tgt_align_fh=tgt_align_fh)
  while True:
    (src_amr_line, src_comments) = amr_metadata.get_amr_line(src_amr_fh)
    if src_amr_line == "":
      break
    (tgt_amr_line, tgt_comments) = amr_metadata.get_amr_line(tgt_amr_fh)
    src_amr = amr_metadata.AmrMeta.from_parse(src_amr_line, src_comments)
    tgt_amr = amr_metadata.AmrMeta.from_parse(tgt_amr_line, tgt_comments)
    assert src_amr.metadata['id'] == tgt_amr.metadata['id']
    cur_id = src_amr.metadata['id']

    src_sent = src_amr.metadata['tok']
    tgt_sent = tgt_amr.metadata['tok']

    amr_graphs = hilight_disagreement([tgt_amr], src_amr, aligner=aligner)
    if json_fh:
          json_fh.write(json_graph.dumps(amr_graphs[0]) + '\n')
    ag = nx.to_agraph(amr_graphs[0])
    ag.layout(prog='dot')
    ag.draw('%s/%s.png' % (args.outdir, cur_id))

    if (args.verbose):
      print("ID: %s\n Sentence: %s\n Sentence: %s" % (cur_id, src_sent, tgt_sent))
    #raw_input("Press enter to continue: ")

  src_amr_fh.close()  
  tgt_amr_fh.close()
  src2tgt_fh.close()
  tgt2src_fh.close()
  if json_fh:
    json_fh.close()


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
  parser.add_argument('--num_align_read',
    help='N to read from GIZA NBEST file.')
  parser.add_argument('--num_aligned_in_file',
    help='N printed to GIZA NBEST file.')
  parser.add_argument('-j', '--json',
    help='File to dump json graphs to.')
  # TODO make interactive option and option to process a specific range
  args = parser.parse_args(remaining_argv)

  if (args.bitext):
    xlang_main(args)
  else:
    monolingual_main(args)
