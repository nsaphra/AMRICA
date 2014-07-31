#!/usr/bin/env python

"""
amr.py

This file is from the code for smatch, available at:

http://amr.isi.edu/download/smatch-v1.0.tar.gz
http://amr.isi.edu/smatch-13.pdf
"""

import sys
from collections import defaultdict


class AMR(object):

  def __init__(
          self,
          var_list=None,
          var_value_list=None,
          link_list=None,
          const_link_list=None,
          path2label=None):
    """
    path2label: maps 0.1.0 to the label (inst or const) of the 0-indexed child
      of the 1-indexed child of the 0th node (head)
    """
    if var_list is None:
      self.nodes = []  # AMR variables
      self.root = None
    else:
      self.nodes = var_list[:]
      if len(var_list) != 0:
        self.root = var_list[0]
      else:
        self.root = None
    if var_value_list is None:
      self.var_values = []
    else:
      self.var_values = var_value_list[:]
    if link_list is None:
      # connections between instances  #adjacent list representation
      self.links = []
    else:
      self.links = link_list[:]
    if const_link_list is None:
      self.const_links = []
    else:
      self.const_links = const_link_list[:]
    if path2label is None:
      self.path2label = {}
    else:
      self.path2label = path2label

  def add_node(node_value):
    self.nodes.append(node_value)

  def rename_node(self, prefix):
    var_map_dict = {}
    for i in range(0, len(self.nodes)):
      var_map_dict[self.nodes[i]] = prefix + str(i)
    for i, v in enumerate(self.nodes):
      self.nodes[i] = var_map_dict[v]
    for i, d in enumerate(self.links):
      new_dict = {}
      for k, v in d.items():
        new_dict[var_map_dict[k]] = v
      self.links[i] = new_dict

  def get_triples(self):
    """Get the triples in two list: instance_triple, relation_triple"""
    instance_triple = []
    relation_triple = []
    for i in range(len(self.nodes)):
      instance_triple.append(("instance", self.nodes[i], self.var_values[i]))
      for k, v in self.links[i].items():
        relation_triple.append((v, self.nodes[i], k))
      for k2, v2 in self.const_links[i].items():
        relation_triple.append((k2, self.nodes[i], v2))
    return (instance_triple, relation_triple)

  def get_triples2(self):
    """Get the triples in three lists: instance_triple, relation (two variables) triple, and relation (one variable) triple"""
    instance_triple = []
    relation_triple1 = []
    relation_triple2 = []
    for i in range(len(self.nodes)):
      instance_triple.append(("instance", self.nodes[i], self.var_values[i]))
      for k, v in self.links[i].items():
        relation_triple2.append((v, self.nodes[i], k))
      for k2, v2 in self.const_links[i].items():
        relation_triple1.append((k2, self.nodes[i], v2))
    return (instance_triple, relation_triple1, relation_triple2)

  def __str__(self):
    """Output AMR string"""
    for i in range(len(self.nodes)):
      print "Variable", i, self.nodes[i]
      print "Dependencies:"
      for k, v in self.links[i].items():
        print "Variable", k, " via ", v
      for k2, v2 in self.const_links[i].items():
        print "Attribute:", k2, "value", v2

  def __repr__(self):
    return self.__str__()

  def out_amr(self):
    self.__str__()

  @staticmethod
  def parse_AMR_line(line, xlang=False):
    # set xlang True if you want consts represented as variable nodes with
    # instance labels
    # significant symbol just encountered: 1 for (, 2 for :, 3 for /
    state = -1
    stack = []  # variable stack
    cur_charseq = []  # current processing char sequence
    var_dict = {}  # key: var name value: var value
    var_list = []  # variable name list (order: occurence of the variable
    # key: var name:  value: list of (attribute name, other variable)
    var_attr_dict1 = defaultdict(list)
    # key:var name, value: list of (attribute name, const value)
    var_attr_dict2 = defaultdict(list)
    cur_attr_name = ""  # current attribute name
    attr_list = []  # each entry is an attr dict
    in_quote = False
    curr_path = ['0']
    path2label = {}
    path_lookup = {}  # (var, reln, const) to path key

    def remove_from_paths(path):
      """ Adjust all paths in path2label by removing the node at path
          (and any descdendants) """
      node_ind = int(path[-1])
      depth = len(path) - 1
      prefix = '.'.join(path[:-1]) + '.'
      # remove node from path2label keys
      new_path2label = {}
      for (k, v) in path2label.items():
        if k.startswith(prefix):
          k_arr = k.split('.')
          curr_ind = int(k_arr[depth])
          if curr_ind == node_ind:
            continue  # deleting node
          elif curr_ind > node_ind:
            # node index moves down by 1 since middle node removed
            k_arr[depth] = str(curr_ind - 1)
            new_path2label['.'.join(k_arr)] = v
            continue
        new_path2label[k] = v
      return new_path2label

      # remove node from path_lookup vals
      for (k, v) in path_lookup.items():
        if v[:depth] == path[:depth]:
          curr_ind = int(v[depth])
          if curr_ind == node_ind:
            del path_lookup[k]
          if curr_ind > node_ind:
            v[depth] = str(curr_ind - 1)

    for i, c in enumerate(line.strip()):
      if c == " ":
        if in_quote:
          cur_charseq.append('_')
          continue
        if state == 2:
          cur_charseq.append(c)
        continue
      elif c == "\"":
        if in_quote:
          in_quote = False
        else:
          in_quote = True
      elif c == "(":
        if in_quote:
          continue
        if state == 2:
          if cur_attr_name != "":
            print >> sys.stderr, "Format error when processing ", line[0:i + 1]
            return None
          cur_attr_name = "".join(cur_charseq).strip()
          cur_charseq[:] = []
        state = 1
      elif c == ":":
        if in_quote:
          continue
        if state == 3:  # (...:
          var_value = "".join(cur_charseq)
          cur_charseq[:] = []
          cur_var_name = stack[-1]
          var_dict[cur_var_name] = var_value
          path2label['.'.join(curr_path)] = var_value
          curr_path.append('0')
        elif state == 2:  # : ...:
          temp_attr_value = "".join(cur_charseq)
          cur_charseq[:] = []
          parts = temp_attr_value.split()
          if len(parts) < 2:
            print >> sys.stderr, "Error in processing", line[0:i + 1]
            return None
          attr_name = parts[0].strip()
          attr_value = parts[1].strip()
          if len(stack) == 0:
            print >> sys.stderr, "Error in processing", line[
                :i], attr_name, attr_value
            return None
          # TODO should all labels in quotes be consts?
          if attr_value not in var_dict:
            var_attr_dict2[stack[-1]].append((attr_name, attr_value))
            path2label['.'.join(curr_path)] = attr_value
            path_lookup[
                (stack[-1], attr_name, attr_value)] = [i for i in curr_path]
            curr_path[-1] = str(int(curr_path[-1]) + 1)
          else:
            var_attr_dict1[stack[-1]].append((attr_name, attr_value))
        else:
          curr_path[-1] = str(int(curr_path[-1]) + 1)
        state = 2
      elif c == "/":
        if in_quote:
          continue
        if state == 1:
          variable_name = "".join(cur_charseq)
          cur_charseq[:] = []
          if variable_name in var_dict:
            print >> sys.stderr, "Duplicate variable ", variable_name, " in parsing AMR"
            return None
          stack.append(variable_name)
          var_list.append(variable_name)
          if cur_attr_name != "":
            if not cur_attr_name.endswith("-of"):
              var_attr_dict1[stack[-2]].append((cur_attr_name, variable_name))
            else:
              var_attr_dict1[variable_name].append(
                  (cur_attr_name[:-3], stack[-2]))
            cur_attr_name = ""
        else:
          print >> sys.stderr, "Error in parsing AMR", line[0:i + 1]
          return None
        state = 3
      elif c == ")":
        if in_quote:
          continue
        if len(stack) == 0:
          print >> sys.stderr, "Unmatched parathesis at position", i, "in processing", line[
              0:i + 1]
          return None
        if state == 2:
          temp_attr_value = "".join(cur_charseq)
          cur_charseq[:] = []
          parts = temp_attr_value.split()
          if len(parts) < 2:
            print >> sys.stderr, "Error processing", line[
                :i + 1], temp_attr_value
            return None
          attr_name = parts[0].strip()
          attr_value = parts[1].strip()
          if cur_attr_name.endswith("-of"):
            var_attr_dict1[variable_name].append(
                (cur_attr_name[:-3], stack[-2]))
          elif attr_value not in var_dict:
            var_attr_dict2[stack[-1]].append((attr_name, attr_value))
          else:
            var_attr_dict1[stack[-1]].append((attr_name, attr_value))
          path2label['.'.join(curr_path)] = attr_value
          path_lookup[
              (stack[-1], attr_name, attr_value)] = [i for i in curr_path]
          curr_path.pop()
        elif state == 3:
          var_value = "".join(cur_charseq)
          cur_charseq[:] = []
          cur_var_name = stack[-1]
          var_dict[cur_var_name] = var_value
          path2label['.'.join(curr_path)] = var_value
        else:
          curr_path.pop()
        stack.pop()
        cur_attr_name = ""
        state = 4
      else:
        cur_charseq.append(c)
    # create var_list, link_list, attribute
    # keep original variable name.
    var_value_list = []
    link_list = []
    const_attr_list = []  # for monolingual mode

    # xlang mode variables
    const_cnt = 0
    const_var_list = []
    const_var_value_list = []
    const_link_list = []

    for v in var_list:
      if v not in var_dict:
        print >> sys.stderr, "Error: variable value not found", v
        return None
      else:
        var_value_list.append(var_dict[v])
      link_dict = {}
      const_dict = {}
      if v in var_attr_dict1:
        for v1 in var_attr_dict1[v]:
          link_dict[v1[1]] = v1[0]
      if v in var_attr_dict2:
        for v2 in var_attr_dict2[v]:
          const_lbl = v2[1]
          if v2[1][0] == "\"" and v2[1][-1] == "\"":
            const_lbl = v2[1][1:-1]
          elif v2[1] in var_dict:
            # not the first occurrence of this child var
            link_dict[v2[1]] = v2[0]
            path2label = remove_from_paths(path_lookup[(v, v2[0], v2[1])])
            continue

          if xlang:
            const_var = '_CONST_%d' % const_cnt
            const_cnt += 1
            var_dict[const_var] = const_lbl
            const_var_list.append(const_var)
            const_var_value_list.append(const_lbl)
            const_link_list.append({})
            link_dict[const_var] = v2[0]
          else:
            const_dict[v2[0]] = const_lbl

      link_list.append(link_dict)
      if not xlang:
        const_attr_list.append(const_dict)
      link_list[0][var_list[0]] = "TOP"
    if xlang:
      var_list += const_var_list
      var_value_list += const_var_value_list
      link_list += const_link_list
      const_attr_list = [{} for v in var_list]
    result_amr = AMR(
        var_list,
        var_value_list,
        link_list,
        const_attr_list,
        path2label)
    return result_amr
