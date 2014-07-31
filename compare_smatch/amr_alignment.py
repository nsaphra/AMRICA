"""
amr_alignment.py

Author: Naomi Saphra (nsaphra@jhu.edu)
Copyright(c) 2014

Builds a weighted mapping of tokens between parallel sentences for use in
weighted cross-language Smatch alignment.
Takes in an output file from GIZA++ (specified in construction functions).
"""

from collections import defaultdict
from pynlpl.formats.giza import GizaSentenceAlignment
import re

class Amr2AmrAligner(object):
  def __init__(self, num_best=5, num_best_in_file=-1, src2tgt_fh=None, tgt2src_fh=None):
    if src2tgt_fh == None or tgt2src_fh == None:
      self.is_default = True
      self.node_weight_fn = self.dflt_node_weight_fn
      self.edge_weight_fn = self.dflt_edge_weight_fn
    else:
      self.is_default = False
      self.node_weight_fn = None
      self.edge_weight_fn = self.xlang_edge_weight_fn
    self.src2tgt_fh = src2tgt_fh
    self.tgt2src_fh = tgt2src_fh
    self.amr2amr = {}
    self.num_best = num_best
    self.num_best_in_file = num_best_in_file
    self.last_nbest_line = {self.src2tgt_fh:None, self.tgt2src_fh:None}
    if num_best_in_file < 0:
      self.num_best_in_file = num_best
    assert self.num_best_in_file >= self.num_best

  def set_amrs(self, tgt_amr, src_amr):
    if self.is_default:
      return

    self.tgt_toks = tgt_amr.metadata['tok'].strip().split()
    self.src_toks = src_amr.metadata['tok'].strip().split()

    sent2sent_union = align_sent2sent_union(self.tgt_toks, self.src_toks,
      self.get_nbest_alignments(self.src2tgt_fh), self.get_nbest_alignments(self.tgt2src_fh))

    if 'alignments' in tgt_amr.metadata:
      amr2sent_tgt = align_amr2sent_jamr(tgt_amr, self.tgt_toks, tgt_amr.metadata['alignments'].strip().split())
    else:
      amr2sent_tgt = align_amr2sent_dflt(tgt_amr, self.tgt_toks)
    if 'alignments' in src_amr.metadata:
      amr2sent_src = align_amr2sent_jamr(src_amr, self.src_toks, src_amr.metadata['alignments'].strip().split())
    else:
      amr2sent_src = align_amr2sent_dflt(src_amr, self.src_toks)

    self.amr2amr = defaultdict(float)
    for (tgt_lbl, tgt_scores) in amr2sent_tgt.items():
      for (src_lbl, src_scores) in amr2sent_src.items():
        if src_lbl.lower() == tgt_lbl.lower():
          self.amr2amr[(tgt_lbl, src_lbl)] += 1.0
          continue
        for (t, t_score) in enumerate(tgt_scores):
          for (s, s_score) in enumerate(src_scores):
            score = t_score * s_score * sent2sent_union[t][s]
            if score > 0:
              self.amr2amr[(tgt_lbl, src_lbl)] += score

    self.node_weight_fn = lambda t,s : self.amr2amr[(t, s)]

  def const_map_fn(self, const):
    """ Get all const strings from source amr that could map to target const """
    const_matches = [const]
    for (t,s) in filter(lambda (t,s): t == const, self.amr2amr):
      if self.node_weight_fn(t,s) > 0: # weight > 0
        const_matches.append(s)
    return sorted(const_matches, key=lambda x: self.node_weight_fn(const, x), reverse=True)

  @staticmethod
  def dflt_node_weight_fn(tgt_label, src_label):
    return 1.0 if tgt_label.lower() == src_label.lower() else 0.0

  @staticmethod
  def dflt_edge_weight_fn(tgt_label, src_label):
    return 1.0 if tgt_label.lower() == src_label.lower() else 0.0

  def xlang_edge_weight_fn(self, tgt_label, src_label):
    tgt = tgt_label.lower()
    src = src_label.lower()
    if tgt == src:
      # operand edges are all equivalent
      #TODO make this an RE instead?
      return 1.0
    if tgt.startswith("op") and src.startswith("op"):
      return 0.9 # frumious hack to favor similar op edges
    return 0.0

  def get_nbest_alignments(self, fh):
    """ Read an entry from the giza alignment .A3 NBEST file. """
    aligns = []
    curr_sent = -1
    start_ind = 0
    if self.last_nbest_line[fh]:
      if self.num_best > 0:
        aligns.append(self.last_nbest_line[fh])
      start_ind = 1
      curr_sent = self.last_nbest_line[fh][0].index
      self.last_nbest_line[fh] = None

    for ind in range(start_ind, self.num_best_in_file):
      meta_line = fh.readline()
      if meta_line == "":
        if len(aligns) == 0:
          return None
        else:
          break

      meta = re.match("# Sentence pair \((\d+)\) "+
        "source length (\d+) target length (\d+) "+
        "alignment score : (.+)", meta_line)
      if not meta:
        raise Exception
      sent = int(meta.group(1))
      if curr_sent < 0:
        curr_sent = sent
      score = float(meta.group(4))

      tgt_line = fh.readline()
      src_line = fh.readline()
      if sent != curr_sent:
        self.last_nbest_line[fh] = (GizaSentenceAlignment(src_line, tgt_line, sent), score)
        break
      if ind < self.num_best:
        aligns.append((GizaSentenceAlignment(src_line, tgt_line, sent), score))
    return aligns

default_aligner = Amr2AmrAligner()

def get_all_labels(amr):
  ret = [v for v in amr.var_values]
  for l in amr.const_links:
    ret += [v for (k,v) in l.items()]
  return ret

def align_amr2sent_dflt(amr, sent):
  labels = get_all_labels(amr)
  align = {l:[0.0 for tok in sent] for l in labels}
  for label in labels:
    lbl = label.lower()
    # checking for multiwords / bad segmentation
    # ('_' replaces ' ' in multiword quotes)
    # TODO just fix AMR format parser to deal with spaces in quotes
    possible_toks = lbl.split('_')
    possible_toks.append(lbl)

    matches = [t_ind for (t_ind, t) in enumerate(sent) if t.lower() in possible_toks]
    for t_ind in matches:
      align[label][t_ind] = 1.0 / len(matches)
  return align

def parse_jamr_alignment(chunk):
  (tok_range, nodes_str) = chunk.split('|')
  (start_tok, end_tok) = tok_range.split('-')
  node_list = nodes_str.split('+')
  return (int(start_tok), int(end_tok), node_list)

def align_label2toks_en(label, sent, weights, toks_to_align):
  """
  label: node label to map
  sent: token list to map label to
  weights: list to be modified with new weights
  default_full: set True to have the default distribution sum to 1 instead of 0
  return list mapping token index to match weight
  """
  # TODO frumious hack. should set up actual stemmer sometime.

  lbl = label.lower()
  stem = lbl
  wordnet = re.match("(.+)-\d\d", lbl)
  if wordnet:
    stem = wordnet.group(1)
  if len(stem) > 4: # arbitrary
    if len(stem) > 5:
      stem = stem[:-2]
    else:
      stem = stem[:-1]

  def is_match(tok):
    return tok == lbl or \
      (len(tok) >= len(stem) and tok[:len(stem)] == stem)

  matches = [t_ind for t_ind in toks_to_align if is_match(sent[t_ind].lower())]
  if len(matches) == 0:
    matches = toks_to_align
  for t_ind in matches:
    weights[t_ind] += 1.0 / len(matches)
  return weights

def align_amr2sent_jamr(amr, sent, jamr_line):
  """
  amr: an amr to map nodes to sentence toks
  sent: sentence array of toks
  jamr_line: metadata field 'alignments', aligned with jamr
  return dict mapping amr node labels to match weights for each tok in sent
  """
  labels = get_all_labels(amr)
  labels_remain = {label:labels.count(label) for label in labels}
  tokens_remain = set(range(len(sent)))
  align = {l:[0.0 for tok in sent] for l in labels}

  for chunk in jamr_line:
    (start_tok, end_tok, node_list) = parse_jamr_alignment(chunk)
    for node_path in node_list:
      label = amr.path2label[node_path]
      toks_to_align = range(start_tok, end_tok)
      align[label] = align_label2toks_en(label, sent, align[label], toks_to_align)
      labels_remain[label] -= 1
      for t in toks_to_align:
        tokens_remain.discard(t)

  #TODO should really switch from a label-token-label alignment model to node-token-node
  for label in labels_remain:
    if labels_remain[label] > 0:
      align[label] = align_label2toks_en(label, sent, align[label], tokens_remain)
  for label in align:
    z = sum(align[label])
    if z == 0:
      continue
    align[label] = [w/z for w in align[label]]
  return align

def align_sent2sent(tgt_toks, src_toks, alignment_scores):
  z = sum([s for (a,s) in alignment_scores])
  tok_align = [[0.0 for s in src_toks] for t in tgt_toks]
  for (align, score) in alignment_scores:
    for srcind, tgtind in align.alignment:
      if tgtind >= 0 and srcind >= 0:
        tok_align[tgtind][srcind] += score

  for targetind, targettok in enumerate(tgt_toks):
    for sourceind, sourcetok in enumerate(src_toks):
      tok_align[targetind][sourceind] /= z
  return tok_align

def align_sent2sent_union(tgt_toks, src_toks, src2tgt, tgt2src):
  src2tgt_align = align_sent2sent(tgt_toks, src_toks, src2tgt)
  tgt2src_align = align_sent2sent(src_toks, tgt_toks, tgt2src)

  tok_align = [[0.0 for s in src_toks] for t in tgt_toks]
  for tgtind, tgttok in enumerate(tgt_toks):
    for srcind, srctok in enumerate(src_toks):
      tok_align[tgtind][srcind] = \
        (src2tgt_align[tgtind][srcind] + tgt2src_align[srcind][tgtind]) / 2.0
  return tok_align
