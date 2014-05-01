#!/usr/bin/env python
"""
Author: Naomi Saphra (nsaphra@jhu.edu)
Read AMR file in while also processing metadata in comments
"""

from smatch.amr import AMR
import re

class AmrMeta(AMR):
  def __init__(self, var_list=None, var_value_list=None,
               link_list=None, const_link_list=None,
               base_amr=None, metadata={}):
    if base_amr is None:
      super(AmrMeta, self).__init__(var_list, var_value_list, 
                                    link_list, const_link_list)
    else:
      self.nodes = base_amr.nodes
      self.root = base_amr.root
      self.var_values = base_amr.var_values
      self.links = base_amr.links
      self.const_links = base_amr.const_links

    self.metadata = metadata

  @classmethod
  def from_parse(cls, annotation_line, comment_lines):
    metadata = {}
    for l in comment_lines:
      matches = re.findall(r'::(\S+)\s([^:]+)', l)
      for m in matches:
        metadata[m[0]] = m[1].strip()

    base_amr = AMR.parse_AMR_line(annotation_line)
    return cls(base_amr=base_amr, metadata=metadata)

  def add_alignment_weights():
    raise NotImplementedError