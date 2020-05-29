#!/usr/bin/env python3
from civet import __version__
import argparse
import os.path
import snakemake
import sys
from tempfile import gettempdir
import tempfile
import pprint
import json
import csv
import setuptools
from Bio import SeqIO

from . import _program

"""
Need query_csv, metadata, fasta (opt)
"""


thisdir = os.path.abspath(os.path.dirname(__file__))
cwd = os.getcwd()

def main(sysargs = sys.argv[1:]):

    parser = argparse.ArgumentParser(prog = _program, 
    description='civet: Cluster Investivations Viral Epidemiology Tool', 
    usage='''civet <query> [options]''')

    parser.add_argument('query')
    parser.add_argument('-f','--fasta', action="store",help="Optional fasta query.")
    parser.add_argument('-o','--outdir', action="store",help="Output directory. Default: current working directory")
    parser.add_argument('-n', '--dry-run', action='store_true',help="Go through the motions but don't actually run")
    parser.add_argument('-f', '--force', action='store_true',help="Overwrite all output",dest="force")
    parser.add_argument('--tempdir',action="store",help="Specify where you want the temp stuff to go. Default: $TMPDIR")
    parser.add_argument('-t', '--threads', action='store',type=int,help="Number of threads")
    parser.add_argument("--verbose",action="store_true",help="Print lots of stuff to screen")
    parser.add_argument("-v","--version", action='version', version=f"civet {__version__}")
    # parser.add_argument("-lv","--lineages-version", action='version', version=f"lineages {lineages.__version__}",help="show lineages's version number and exit")

    if len(sysargs)<1:
        parser.print_help()
        sys.exit(-1)
    else:
        args = parser.parse_args(sysargs)

    # find the Snakefile
    snakefile = os.path.join(thisdir, 'scripts','Snakefile')
    if not os.path.exists(snakefile):
        sys.stderr.write('Error: cannot find Snakefile at {}\n'.format(snakefile))
        sys.exit(-1)
    else:
        print("Found the snakefile")

    # find the query csv
    query = os.path.join(cwd, args.query)
    if not os.path.exists(query):
        sys.stderr.write('Error: cannot find query at {}\n'.format(query))
        sys.exit(-1)
    else:
        print(f"The query file is {query}")

    # find the query fasta
    if args.fasta:
        fasta = os.path.join(cwd, args.fasta)
        if not os.path.exists(fasta):
            sys.stderr.write('Error: cannot find fasta query at {}\n'.format(fasta))
            sys.exit(-1)
        else:
            print(f"The fasta file is {fasta}")
    else:
        print("No fasta loaded")
        fasta = ""

    # default output dir
    outdir = ''
    if args.outdir:
        outdir = os.path.join(cwd, args.outdir)
    else:
        outdir = cwd

    tempdir = ''
    if args.tempdir:
        to_be_dir = os.path.join(cwd, args.tempdir)
        if not os.path.exists(to_be_dir):
            os.mkdir(to_be_dir)
        temporary_directory = tempfile.TemporaryDirectory(suffix=None, prefix=None, dir=to_be_dir)
        tempdir = temporary_directory.name
    else:
        temporary_directory = tempfile.TemporaryDirectory(suffix=None, prefix=None, dir=None)
        tempdir = temporary_directory.name

    """ 
    QC steps:
    1) check csv header
    2) check fasta file N content
    3) write a file that contains just the seqs to run
    """
    fields = []
    queries = []
    with open(query, newline="") as f:
        reader = csv.DictReader(f)
        for field in reader.fieldnames:
            fields.append(field)
        for row in reader:
            queries.append(row["name"])

    # how many threads to pass
    if args.threads:
        threads = args.threads
    else:
        threads = 1
    print("Number of threads is", threads)

    config = {
        "query":query,
        "fields":",".join(fields),
        "outdir":outdir,
        "tempdir":tempdir,
        "trim_start":,
        "trim_end":,
        "fasta":fasta
        }

    if args.fasta:
        do_not_run = []
        run = []
        for record in SeqIO.parse(query, "fasta"):
            if len(record) <args.minlen:
                record.description = record.description + f" fail=seq_len:{len(record)}"
                do_not_run.append(record)
                print(record.id, "\tsequence too short")
            else:
                num_N = str(record.seq).upper().count("N")
                prop_N = round((num_N)/len(record.seq), 2)
                if prop_N > args.maxambig: 
                    record.description = record.description + f" fail=N_content:{prop_N}"
                    do_not_run.append(record)
                    print(f"{record.id}\thas an N content of {prop_N}")
                else:
                    run.append(record)

        post_qc_query = os.path.join(tempdir, 'query.post_qc.fasta')
        with open(post_qc_query,"w") as fw:
            SeqIO.write(run, fw, "fasta")
        qc_fail = os.path.join(tempdir,'query.failed_qc.fasta')
        with open(qc_fail,"w") as fw:
            SeqIO.write(do_not_run, fw, "fasta")

        config["post_qc_query"]:post_qc_query
        config["qc_fail"]:qc_fail

    if args.force:
        config["force"]="forceall"
    # find the data
    data_dir = ""
    if args.data:
        data_dir = os.path.join(cwd, args.data)
    else:
        data_dir = os.path.join(thisdir,"data")

    # find the data files
    cog_metadata = os.path.join(data_dir, "cog_gisaid.csv")
    cog_seqs = os.path.join(data_dir, "cog_gisaid.fasta")
    cog_lineage_trees = os.path.join(data_dir, "lineage_trees")
    reference_fasta = os.path.join(data_dir, "reference.fasta")
    
    if not os.path.exists(cog_metadata) or not os.path.exists(cog_seqs) or not os.path.exists(cog_lineage_trees):
        sys.stderr.write('Error: cannot find data at {}\n'.format(data_dir))
        sys.exit(-1)
    else:
        config["cog_metadata"] = cog_metadata
        config["cog_seqs"] = cog_seqs
        config["cog_lineage_trees"] = cog_lineage_trees
        config["reference_fasta"] = reference_fasta

    if args.verbose:
        quiet_mode = False
    else:
        quiet_mode = True

    # run subtyping
    status = snakemake.snakemake(snakefile, printshellcmds=True,
                                 dryrun=args.dry_run, forceall=args.force,force_incomplete=True,
                                 config=config, cores=threads,lock=False,quiet=quiet_mode,workdir=tempdir
                                 )

    if status: # translate "success" into shell exit code of 0
       return 0

    return 1

if __name__ == '__main__':
    main()