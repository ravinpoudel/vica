#!/usr/bin/env python3
'''prodigal.py: a module to call genes with prodigal then count codon usage
and transform into centered log ratio'''

import subprocess
import os
import numpy as np
from collections import OrderedDict
from collections import defaultdict
from functools import reduce
import math
from Bio import SeqIO
import tempfile
import csv

codon_list = ["TTT", "TCT", "TAT", "TGT",
              "TTC", "TCC", "TAC", "TGC",
              "TTA", "TCA", "TAA", "TGA",
              "TTG", "TCG", "TAG", "TGG",
              "CTT", "CCT", "CAT", "CGT",
              "CTC", "CCC", "CAC", "CGC",
              "CTA", "CCA", "CAA", "CGA",
              "CTG", "CCG", "CAG", "CGG",
              "ATT", "ACT", "AAT", "AGT",
              "ATC", "ACC", "AAC", "AGC",
              "ATA", "ACA", "AAA", "AGA",
              "ATG", "ACG", "AAG", "AGG",
              "GTT", "GCT", "GAT", "GGT",
              "GTC", "GCC", "GAC", "GGC",
              "GTG", "GCG", "GAG", "GGG"]



def clr(composition):
    def geomean(vector):
        a = np.array(vector)
        return a.prod()**(1.0/len(a))
    gm = geomean(composition)
    return list(map(lambda x: math.log(x/gm), composition))



def call_genes(file, outfile, tempdir):
    '''Runs prodigal calling genes'''
    options = ["prodigal",
               "-i", file,
               "-p", "meta",
               "-d", "outfile",
               "-o", "genecalls.txt"]
    sendsketchout = subprocess.run(options, stderr=subprocess.PIPE)
    return sendsketchout.stderr.decode('utf-8')


def _gene_to_codon(genestring):
    '''Converts a DNA sequence string to a list of codons'''
    try:
        if len(genestring)>=3:
            f1 = [genestring[i:i+3] for i in range(0, len(genestring), 3)]
            if not len(f1[-1]) == 3:
                f1 = f1[:-1]
            return f1
    except ValueError:
        print("Warning: could not convert gene sequence to a list for codon counting")
        return []

def _codon_to_dict(genestring, offset):
    '''counts codons in a gene string, with a reading frame offest returning
       codon counts as a dict.'''
    framen = _gene_to_codon(genestring[offset:])
    cdict = {}
    for codon in framen:
        if not codon in cdict:
            cdict[codon] = 1
        else:
            cdict[codon] += 1
    return cdict

def get_id_list(fasta):
    '''extract the ids from a fasta file'''
    idlist = []
    with open(fasta, 'r') as f:
        for line in f:
            if line.startswith(">"):
                idlist.append(line.strip().split()[0])
    return idlist

def _parse_prodigal_id_from_biopython(id):
    '''strips off prodigal gene annotations and returns the id as it was in the contig file'''
    return '_'.join(str(id).split('_')[:-1])

def count_dict_to_clr_array(count_dict, codon_list, pseudocount=0.01):
    '''Takes a dictionary of counts where the key is the upper case codon,
       orders them by codon, and performs a clr transformation returning a 1D np array'''
    output_list = []
    for i in codon_list:
        if i in count_dict:
            output_list.append(count_dict[i])
        else:
            output_list.append(0)
    output_list = [x + pseudocount for x in output_list]
    return clr(output_list)

def dsum(*dicts):
    ret = defaultdict(int)
    for d in dicts:
        for k, v in d.items():
            ret[k] += v
    return dict(ret)

def count_codon_in_gene(record, cdict={}):
    '''takes a biopython sequence record and optionally a defaultdict and
       returns a defaultdict with the counts for the three codon frames adding
       them to the existing default dict if one was supplied.'''
    seq = str(record.seq)
    d1 = {}
    d2 = {}
    for i in range(3):
        d1[i] = _codon_to_dict(genestring=seq, offset=i)
    for i in range(3):
        if i in cdict:
            d2[i] = dsum(cdict[i], d1[i])
        else:
            d2[i] = d1[i]
    return d2


def count_codons(seqio_iterator, csv_writer_instance):

    def record_line(id, codon_dict, csv_writer_instance):
        l0 = count_dict_to_clr_array(codon_dict[0], codon_list)
        l1 = count_dict_to_clr_array(codon_dict[1], codon_list)
        l2 = count_dict_to_clr_array(codon_dict[2], codon_list)
        id_and_data = [id]
        id_and_data.extend(list(np.concatenate((l0, l1, l2))))
        csv_writer_instance.writerow(id_and_data)

    print("running count_codons")
    last_base_id = None
    codon_dict = {}
    for record in seqio_iterator:
        base_id = _parse_prodigal_id_from_biopython(record.id)
        if base_id == last_base_id:
                codon_dict = count_codon_in_gene(record=record, cdict=codon_dict)
            # print("in loop 1")
        elif base_id is not last_base_id:
            if codon_dict != {}:
                record_line(id=last_base_id, codon_dict=codon_dict, csv_writer_instance=csv_writer_instance)
            codon_dict =count_codon_in_gene(record=record, cdict={})
            last_base_id = base_id
    if codon_dict != {}:
        record_line(id=base_id, codon_dict=codon_dict, csv_writer_instance=csv_writer_instance)


def contigs_to_feature_file(infile, outfile):
    seqs = SeqIO.parse(infile, 'fasta')
    with open(outfile, 'w') as csvfile:
        csv_writer_instance = csv.writer(csvfile)
        count_codons(seqio_iterator= seqs, csv_writer_instance=csv_writer_instance)
