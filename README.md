This is a script for producing and visualizing AMR annotation alignments based on Smatch. It can be used either to visualize basic Smatch alignments or to align AMR annotations for different translations of the same sentence.

 It expects an AMR file with comment sections describing the sentence ID as input, and it outputs a graphviz'd up PNG for each gold-test sentence pair.

For monolingual inter-annotator agreement, `disagree.py` expects an AMR file with different annotations of the same sentence listed consecutively. Each AMR should be annotated with a sentence ID, annotator ID, and the sentence itself. For example:
```
./disagree.py -i input.amr -o output_dir/ -j output.json
```

It will print an AMR graph with red elements for things in the test AMR and not the gold AMR and blue elements for anything in gold and not in test. If you just want to print a graph of a single annotator's AMRs, use a file with only one annotation per sentence.

For bilingual AMR alignment, disagree.py expects two AMR files, one for each language. If an AMR contains a ::alignments field, it will be read as a jamr alignment for the purposes of matching AMRs to the corresponding sentence. Without an alignments field, we assume labels align to tokens that match them by string in the sentence. Two GIZA alignment NBEST files (see GIZA documentation for --nbestalignments flag) are expected as well, one for source-target and one target-source. `disagree.py` takes parameters to describe how many of the nbest alignments should be used and how many should be expected in the file. Example:
```
./disagree.py --bitext -s src.amr -t tgt.amr --align_tgt2src t2s.A3.NBEST --align_src2tgt s2t.A3.NBEST --num_align_read 5 --num_aligned_in_file 20 -o outdir/
```

The script also takes config files with the `-c` flag. See disagree.py documentation for more details. scripts/ contains scripts for analyzing the .json output of the disagree.py aligner.