#!/usr/bin/env python
"""
Author: Naomi Saphra (nsaphra@jhu.edu)

A tool for inspecting AMR data to id patterns of inter-annotator disagreement
or semantic inequivalence.

AMR input file expected in format where comments above each annotation indicate
the sentence like so:

# ::id DF-170-181103-888_2097.1 ::date 2013-09-16T07:15:31 ::annotator ANON-01 ::preferred
# ::tok This is a sentence .
(this / file
  :is (an / AMR))

For monolingual disagreement, all annotations of some sentence should occur
consecutively in the monolingual annotation file. For bilingual, annotations
should be in the same order of sentences between the two files.

For bilingual disagreement, you can include a ::alignments field from jamr to help with
AMR-sentence alignment.
"""

import argparse
import argparse_config
import networkx as nx
from networkx.readwrite import json_graph
import os
from compare_smatch.amr_alignment import Amr2AmrAligner
from compare_smatch.amr_alignment import default_aligner
from smatch import smatch
from collections import defaultdict
import pygraphviz as pgz
import copy
from pynlpl.formats.giza import GizaSentenceAlignment
import codecs
from compare_smatch import amr_metadata
from compare_smatch import smatch_graph
from compare_smatch.smatch_graph import SmatchGraph

cur_sent_id = 0

def hilight_disagreement(test_amrs, gold_amr, iter_num, aligner=default_aligner, gold_aligned_fh=None):
  """
  Input:
    gold_amr: gold AMR object
    test_amrs: list of AMRs to compare to
  Returns list of disagreement graphs for each gold-test AMR pair.
  """

  amr_graphs = []
  smatchgraphs = []
  gold_label=u'b'
  gold_amr.rename_node(gold_label)
  (gold_inst, gold_rel1, gold_rel2) = gold_amr.get_triples2()
  (gold_inst_t, gold_rel1_t, gold_rel2_t) = smatch_graph.amr2dict(gold_inst, gold_rel1, gold_rel2)

  for a in test_amrs:
    aligner.set_amrs(a, gold_amr)
    test_label=u'a'
    a.rename_node(test_label)
    (test_inst, test_rel1, test_rel2) = a.get_triples2()
    if gold_aligned_fh:
      best_match = get_next_gold_alignments(gold_aligned_fh)
      best_match_num = -1.0
    else:
      (best_match, best_match_num) = smatch.get_fh(test_inst, test_rel1, test_rel2,
        gold_inst, gold_rel1, gold_rel2,
        test_label, gold_label,
        node_weight_fn=aligner.node_weight_fn, edge_weight_fn=aligner.edge_weight_fn,
        iter_num=iter_num)

    disagreement = SmatchGraph(test_inst, test_rel1, test_rel2, \
      gold_inst_t, gold_rel1_t, gold_rel2_t, \
      best_match, const_map_fn=aligner.const_map_fn)
    amr_graphs.append((disagreement.smatch2graph(node_weight_fn=aligner.node_weight_fn,
                                                 edge_weight_fn=aligner.edge_weight_fn),
      best_match_num))
    smatchgraphs.append(disagreement)
  return (amr_graphs, smatchgraphs)


def open_output_files(args):
  json_fh = None
  if args.json_out:
    json_fh = codecs.open(args.json_out, 'w', encoding='utf8')
  align_fh = None
  if args.align_out:
    align_fh =  codecs.open(args.align_out, 'w', encoding='utf8')
  return (json_fh, align_fh)


def close_output_files(json_fh, align_fh):
  json_fh and json_fh.close()
  align_fh and align_fh.close()


def get_next_gold_alignments(gold_aligned_fh):
  match_hash = {}
  line = gold_aligned_fh.readline().strip()
  while (line):
    if line.startswith('#'): # comment line
      line = gold_aligned_fh.readline().strip()
      continue
    align = line.split('\t')
    test_ind = int(align[0])
    gold_ind = int(align[3])
    if test_ind >= 0:
      match_hash[test_ind] = gold_ind
    line = gold_aligned_fh.readline().strip()

  match = []
  for (i, (k, v)) in enumerate(sorted(match_hash.items(), key=lambda x: x[0])):
    assert i == k
    match.append(v)
  return match


def get_sent_info(metadata, dflt_id=None):
  """ Return ID, sentence if available, and change metadata to reflect """
  (sent_id, sent) = (None, None)
  if 'tok' in metadata:
    sent = metadata['tok']
  else:
    sent = metadata['snt']

  if 'id' in metadata:
    sent_id = metadata['id']
  elif dflt_id is not None:
    sent_id = dflt_id
  else:
    sent_id = "%d" % cur_sent_id
    cur_sent_id += 1

  (metadata['id'], metadata['tok']) = \
    (sent_id, sent)

  return (sent_id, sent)


def monolingual_main(args):
  infile = codecs.open(args.infile, encoding='utf8')
  gold_aligned_fh = None
  if args.align_in:
    gold_aligned_fh = codecs.open(args.align_in, encoding='utf8')
  (json_fh, align_fh) = open_output_files(args)

  amrs_same_sent = []
  cur_id = ""
  while True:
    (amr_line, comments) = amr_metadata.get_amr_line(infile)
    cur_amr = None
    if amr_line:
      cur_amr = amr_metadata.AmrMeta.from_parse(amr_line, comments)
      get_sent_info(cur_amr.metadata)
      if 'annotator' not in cur_amr.metadata:
        cur_amr.metadata['annotator'] = ''
      if not cur_id:
        cur_id = cur_amr.metadata['id']

    if cur_amr is None or cur_id != cur_amr.metadata['id']:
      gold_amr = amrs_same_sent[0]
      test_amrs = amrs_same_sent[1:]
      if len(test_amrs) == 0:
        test_amrs = [gold_amr] # single AMR view case
        args.num_restarts = 1 # TODO make single AMR view more efficient
      (amr_graphs, smatchgraphs) = hilight_disagreement(test_amrs, gold_amr, args.num_restarts)

      gold_anno = gold_amr.metadata['annotator']
      sent = gold_amr.metadata['tok']

      if (args.verbose):
        print("ID: %s\n Sentence: %s\n gold anno: %s" % (cur_id, sent, gold_anno))

      for (a, (g, score)) in zip(test_amrs, amr_graphs):
        test_anno = a.metadata['annotator']
        if json_fh:
          json_fh.write(json_graph.dumps(g) + '\n')
        if align_fh:
          for sg in smatchgraphs:
            align_fh.write("""# ::id %s\n# ::tok %s\n# ::gold_anno %s\n# ::test_anno %s""" % \
              (cur_id, sent, gold_anno, test_anno))
            align_fh.write('\n'.join(sg.get_text_alignments()) + '\n\n')
        if (args.verbose):
          print("  annotator %s score: %d" % (test_anno, score))

        ag = nx.to_agraph(g)
        ag.graph_attr['label'] = sent
        ag.layout(prog='dot')
        ag.draw('%s/%s_annotated_%s_%s.png' % (args.outdir, cur_id, gold_anno, test_anno))

      amrs_same_sent = []
      if cur_amr is not None:
        cur_id = cur_amr.metadata['id']
      else:
        break

    amrs_same_sent.append(cur_amr)

  infile.close()
  gold_aligned_fh and gold_aligned_fh.close()
  close_output_files(json_fh, align_fh)


def xlang_main(args):
  """ Disagreement graphs for aligned cross-language language. """
  src_amr_fh = codecs.open(args.src_amr, encoding='utf8')
  tgt_amr_fh = codecs.open(args.tgt_amr, encoding='utf8')
  src2tgt_fh = codecs.open(args.align_src2tgt, encoding='utf8')
  tgt2src_fh = codecs.open(args.align_tgt2src, encoding='utf8')
  gold_aligned_fh = None
  if args.align_in:
    gold_aligned_fh = codecs.open(args.align_in, encoding='utf8')
  (json_fh, align_fh) = open_output_files(args)

  amrs_same_sent = []
  aligner = Amr2AmrAligner(num_best=args.num_align_read, num_best_in_file=args.num_aligned_in_file, src2tgt_fh=src2tgt_fh, tgt2src_fh=tgt2src_fh)
  while True:
    (src_amr_line, src_comments) = amr_metadata.get_amr_line(src_amr_fh)
    if src_amr_line == "":
      break
    (tgt_amr_line, tgt_comments) = amr_metadata.get_amr_line(tgt_amr_fh)
    src_amr = amr_metadata.AmrMeta.from_parse(src_amr_line, src_comments, xlang=True)
    tgt_amr = amr_metadata.AmrMeta.from_parse(tgt_amr_line, tgt_comments, xlang=True)
    (cur_id, src_sent) = get_sent_info(src_amr.metadata)
    (tgt_id, tgt_sent) = get_sent_info(tgt_amr.metadata, dflt_id=cur_id)
    assert cur_id == tgt_id

    (amr_graphs, smatchgraphs) = hilight_disagreement([tgt_amr], src_amr, args.num_restarts, aligner=aligner, gold_aligned_fh=gold_aligned_fh)
    if json_fh:
      json_fh.write(json_graph.dumps(amr_graphs[0]) + '\n')
    if align_fh:
      align_fh.write("""# ::id %s\n# ::src_snt %s\n# ::tgt_snt %s\n""" % (cur_id, src_sent, tgt_sent))
      align_fh.write('\n'.join(smatchgraphs[0].get_text_alignments()) + '\n\n')
    if (args.verbose):
      print("ID: %s\n Sentence: %s\n Sentence: %s\n Score: %f" % (cur_id, src_sent, tgt_sent, amr_graphs[0][1]))
    #raw_input("Press enter to continue: ")

    ag = nx.to_agraph(amr_graphs[0][0])
    ag.graph_attr['label'] = "%s\n%s" % (src_sent, tgt_sent)
    ag.layout(prog='dot')
    ag.draw('%s/%s.png' % (args.outdir, cur_id))

  src_amr_fh.close()
  tgt_amr_fh.close()
  src2tgt_fh.close()
  tgt2src_fh.close()
  gold_aligned_fh and gold_aligned_fh.close()
  close_output_files(json_fh, align_fh)


if __name__ == '__main__':
  parser = argparse.ArgumentParser()
  parser.add_argument("-c", "--conf_file", help="Specify config file")
  parser.add_argument('-i', '--infile', help='amr input file')
  parser.add_argument('-o', '--outdir', help='image output directory')
  parser.add_argument('-v', '--verbose', action='store_true')
  parser.add_argument('--no-verbose', action='store_true')
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
  parser.add_argument('--num_align_read', type=int,
    help='N to read from GIZA NBEST file.')
  parser.add_argument('--num_aligned_in_file', type=int, default=1,
    help='N printed to GIZA NBEST file.')
  parser.add_argument('-j', '--json_out',
    help='File to dump json graphs to.')
  parser.add_argument('--num_restarts', type=int, default=5,
    help='Number of random restarts to execute during hill-climbing algorithm.')
  parser.add_argument('--align_out',
    help="Human-readable alignments output file")
  parser.add_argument('--align_in',
    help="Alignments from human-editable text file, as from align_out")
  # TODO make interactive option and option to process a specific range

  args_conf = parser.parse_args()
  if args_conf.conf_file:
    argparse_config.read_config_file(parser, args_conf.conf_file)

  args = parser.parse_args()
  if args.no_verbose:
    args.verbose = False
  if not args.num_align_read:
    args.num_align_read = args.num_aligned_in_file

  if not os.path.exists(args.outdir):
    os.makedirs(args.outdir)

  if (args.bitext):
    xlang_main(args)
  else:
    monolingual_main(args)
