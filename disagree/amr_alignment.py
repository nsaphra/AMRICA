"""
alignments-weight.py

Author: Naomi Saphra (nsaphra@jhu.edu)
Copyright(c) 2014

Builds a weighted mapping of tokens between parallel sentences for use in
weighted cross-language Smatch alignment.
Takes in an output file from GIZA++ (specified in construction functions).
"""

# TODO document
import re
from collections import defaultdict
from pynlpl.formats.giza import GizaSentenceAlignment

class Amr2AmrAligner(object):
  def __init__(self, num_best=5, num_best_in_file=-1, src2tgt_fh=None, tgt2src_fh=None, tgt_align_fh=None):
    if src2tgt_fh == None or tgt2src_fh == None:
      self.is_default = True
      self.weight_fn = self.dflt_weight_fn
    else:
      self.is_default = False
      self.weight_fn = None
    self.src2tgt_fh = src2tgt_fh
    self.tgt2src_fh = tgt2src_fh
    self.tgt_align_fh = tgt_align_fh
    self.amr2amr = {}
    self.num_best = num_best
    self.num_best_in_file = num_best_in_file
    if num_best_in_file < 0:
      self.num_best_in_file = num_best

  def set_amrs(self, tgt_amr, src_amr):
    if self.is_default:
      return

    self.tgt_toks = tgt_amr.metadata['snt'].strip().split()
    self.src_toks = src_amr.metadata['snt'].strip().split()
    tgt_labels = self.get_all_labels(tgt_amr)
    src_labels = self.get_all_labels(src_amr)

    sent2sent_union = align_sent2sent_union(self.tgt_toks, self.src_toks,
      get_nbest_alignments(self.src2tgt_fh, self.num_best), get_nbest_alignments(self.tgt2src_fh, self.num_best))

    tgt_align = get_amr2sent_lines(self.tgt_align_fh)
    amr2sent_tgt = align_amr2sent_en(tgt_labels, self.tgt_toks, tgt_align)
    amr2sent_src = align_amr2sent_dflt(src_labels, self.src_toks)

    self.amr2amr = defaultdict(float)
    for (tgt_lbl, tgt_scores) in amr2sent_tgt.items():
      for (src_lbl, src_scores) in amr2sent_src.items():
        if src_lbl == tgt_lbl:
          self.amr2amr[(tgt_lbl, src_lbl)] = 1.0
          continue
        for (t, t_score) in enumerate(tgt_scores):
          for (s, s_score) in enumerate(src_scores):
            score = t_score * s_score * sent2sent_union[t][s]
            if score > 0:
              self.amr2amr[(tgt_lbl, src_lbl)] += score

    self.weight_fn = lambda t,s : self.amr2amr[(t, s)]

  def const_map_fn(self, const):
    """ Get all const strings from source amr that could map to target const """
    const_matches = [const]
    for (t,s) in filter(lambda (t,s): t == const, self.amr2amr):
      if self.weight_fn(t,s) > 0: # weight > 0
        const_matches.append(s)
    return sorted(const_matches, key=lambda x: self.weight_fn(const, x))

  @staticmethod
  def get_all_labels(amr):
    ret = [v for v in amr.var_values]
    for l in amr.const_links:
      ret += [v for (k,v) in l.items()]
    return ret

  @staticmethod
  def dflt_weight_fn(tgt_label, src_label):
    return 1.0 if tgt_label.lower() == src_label.lower() else 0.0

default_aligner = Amr2AmrAligner()

def get_amr2sent_lines(fh):
  lines = []
  line = fh.readline()
  while line and line.strip():
    data = line.strip().lower()
    line = fh.readline()
    if data.startswith('#'):
      continue
    lines.append(data)
  return lines

def align_amr2sent_dflt(labels, sent):
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

def align_amr2sent_en(labels, sent, align_lines):
  maps = defaultdict(set)
  for line in align_lines:
    data = line.split()
    maps[data[0]] |= set(data[1:])

  align = {l:[0.0 for tok in sent] for l in labels}
  # TODO This is not a final version -- need to get jamr aligner working!
  for label in labels:
    lbl = label.lower()
    stem = lbl
    stem = stem.rstrip('s')
    wordnet = re.match("(.+)-\d\d", lbl)
    if wordnet:
      stem = wordnet.group(1)
    def is_match(tok):
      return tok == lbl or \
        (len(tok) >= len(stem) and tok[:len(stem)] == stem) or \
        tok in maps[lbl]

    matches = [t_ind for (t_ind, t) in enumerate(sent) if is_match(t.lower())]
    for t_ind in matches:
      align[label][t_ind] = 1.0 / len(matches)
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

def get_nbest_alignments(fh, num_nbest):
  """ Read an entry from the giza alignment .A3 NBEST file. """
  aligns = []
  for ind in range(num_nbest):
    meta_line = fh.readline()
    if meta_line == "":
      return None

    meta = re.match("# Sentence pair \((\d+)\) "+
      "source length (\d+) target length (\d+) "+
      "alignment score : (.+)", meta_line)
    if not meta:
      raise Exception
    sent = int(meta.group(1))
    score = float(meta.group(4))
    tgt_line = fh.readline()
    src_line = fh.readline()
    aligns.append((GizaSentenceAlignment(src_line, tgt_line, sent), score))
  return aligns
