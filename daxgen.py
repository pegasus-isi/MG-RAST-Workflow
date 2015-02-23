#!/usr/bin/env python
import sys
import string
import os
from datetime import datetime
from ConfigParser import ConfigParser
from Pegasus.DAX3 import ADAG, Job, File, Link

DAXGEN_DIR = os.path.dirname(os.path.realpath(__file__))

class MGRASTWorkflow(object):

	def __init__(self, outdir, config, mgfile):
		"'outdir' is the directory where the workflow is written, and 'config' is a ConfigParser object"
		self.outdir = outdir
		self.config = config
		self.mgfile = mgfile
		self.daxfile = os.path.join(self.outdir, "dax.xml")
		self.replicas = {}

		# Get all the values from the config file
		self.file_format = config.get("simulation", "file_format")
		self.assembled = config.get("simulation", "assembled")
		self.filter_options = config.get("simulation", "filter_options")
		self.prefix_length = config.get("simulation", "prefix_length")
		self.dereplicate = config.get("simulation", "dereplicate")
		self.m5rna_clust = config.get("simulation", "m5rna_clust")
		self.screen_indexes = config.get("simulation", "screen_indexes")
		self.bowtie = config.get("simulation", "bowtie")
		self.fgs_type = config.get("simulation", "fgs_type")
		self.aa_pid = config.get("simulation", "aa_pid")
		self.ach_annotation_ver = config.get("simulation", "ach_annotation_ver")
		self.rna_pid = config.get("simulation", "rna_pid")


	def add_replica(self, name, path):
		"Add a replica entry to the replica catalog for the workflow"
		url = path
		if url is None:
			url = "gsiftp://${SITE_URL}/${MGRAST_DIR}/predata/%s" % name
		self.replicas[name] = url


	def generate_replica_catalog(self):
		"Write the replica catalog for this workflow to a file"
		path = os.path.join(self.outdir, "rc.template")
		f = open(path, "w")
		try:
			pool = "local"
			for name, url in self.replicas.items():
				if not url.startswith("gsiftp://"):
					url = "file://%s" % url
				f.write('%-30s %-100s pool="%s"\n' % (name, url, pool))
		finally:
			f.close()

	def generate_workflow(self):
		"Generate a workflow (DAX, config files, and replica catalog)"
		ts = datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')
		dax = ADAG("mgrast-prod-%s" % ts)
		
		# These are all the global input files for the workflow
		metagenome = File(self.mgfile)
		self.add_replica(self.mgfile, os.path.abspath(self.mgfile))

		# QC job
		qcJob = Job("wrapper-qc", node_label="wrapper-qc")

		qcJob.addArguments("-input", self.mgfile)
		qcJob.addArguments("-format", self.file_format)
		qcJob.addArguments("-out_prefix", "075")
		qcJob.addArguments("-assembled", self.assembled)
		qcJob.addArguments("-filter_options", self.filter_options)
		qcJob.addArguments("-proc", "8")

		qcJob.uses(metagenome, link=Link.INPUT)
		qcJob.uses("075.assembly.coverage", link=Link.OUTPUT, transfer=False)
		qcJob.uses("075.qc.stats", link=Link.OUTPUT, transfer=False)
		qcJob.uses("075.upload.stats", link=Link.OUTPUT, transfer=False)

		qcJob.profile("globus", "maxwalltime", "60")
		qcJob.profile("globus", "hostcount", "8")
		qcJob.profile("globus", "count", "8")
		dax.addJob(qcJob)

		# Preprocess Job
		preprocessJob = Job("wrapper-preprocess", node_label="wrapper-preprocess")
		preprocessJob.addArguments("-input", self.mgfile)
		preprocessJob.addArguments("-format", self.file_format)
		preprocessJob.addArguments("-out_prefix", "100.preprocess")
		preprocessJob.addArguments("-filter_options", self.filter_options)
		
		preprocessJob.uses(metagenome, link=Link.INPUT)
		preprocessJob.uses("100.preprocess.passed.fna", link=Link.OUTPUT, transfer=False)
		preprocessJob.uses("100.preprocess.removed.fna", link=Link.OUTPUT, transfer=False)

		preprocessJob.profile("globus", "maxwalltime", "20")
		dax.addJob(preprocessJob)

		# Dereplicate Job
		dereplicateJob = Job("wrapper-dereplicate", node_label="wrapper-dereplicate")
		dereplicateJob.addArguments("-input=100.preprocess.passed.fna")
		dereplicateJob.addArguments("-out_prefix=150.dereplication")
		dereplicateJob.addArguments("-prefix_length=%s" % self.prefix_length)
		dereplicateJob.addArguments("-dereplicate=%s" % self.dereplicate)
		dereplicateJob.addArguments("-memory=10")

		dereplicateJob.uses("100.preprocess.passed.fna", link=Link.INPUT)
		dereplicateJob.uses("150.dereplication.passed.fna", link=Link.OUTPUT, transfer=False)
		dereplicateJob.uses("150.dereplication.removed.fna", link=Link.OUTPUT, transfer=False)

		dereplicateJob.profile("globus", "maxwalltime", "10")
		dax.addJob(dereplicateJob)
		dax.depends(dereplicateJob, preprocessJob)

		# Bowtie Screen Job
		bowtieJob = Job("wrapper-bowtie-screen", node_label="wrapper-bowtie-screen")
		bowtieJob.addArguments("-input=150.dereplication.passed.fna")
		bowtieJob.addArguments("-output=299.screen.passed.fna")
		bowtieJob.addArguments("-index=%s" % self.screen_indexes)
		bowtieJob.addArguments("-bowtie=%s" % self.bowtie)
		bowtieJob.addArguments("-proc=8")

		bowtieJob.uses("150.dereplication.passed.fna", link=Link.INPUT)
		bowtieJob.uses("299.screen.passed.fna", link=Link.OUTPUT, transfer=False)

		bowtieJob.profile("globus", "maxwalltime", "30")
		bowtieJob.profile("globus", "hostcount", "8")
		bowtieJob.profile("globus", "count", "8")
		dax.addJob(bowtieJob)
		dax.depends(bowtieJob, dereplicateJob)

		# Genecalling Job
		geneJob = Job("wrapper-genecalling", node_label="wrapper-genecalling")
		geneJob.addArguments("-input=299.screen.passed.fna")
		geneJob.addArguments("-out_prefix=350.genecalling.coding")
		geneJob.addArguments("-type=%s" % self.fgs_type)
		geneJob.addArguments("-size=100")
		geneJob.addArguments("-proc=8")

		geneJob.uses("299.screen.passed.fna", link=Link.INPUT)
		geneJob.uses("350.genecalling.coding.faa", link=Link.OUTPUT, transfer=False)
		geneJob.uses("350.genecalling.coding.fna", link=Link.OUTPUT, transfer=False)

		geneJob.profile("globus", "maxwalltime", "30")
		geneJob.profile("globus", "hostcount", "8")
		geneJob.profile("globus", "count", "8")
		dax.addJob(geneJob)
		dax.depends(geneJob, bowtieJob)

		# Cluster (Genecalling) Job
		cluster1Job = Job("wrapper-cluster", node_label="wrapper-cluster")
		cluster1Job.addArguments("-input=350.genecalling.coding.faa")
		cluster1Job.addArguments("-out_prefix=550.cluster")
		cluster1Job.addArguments("-aa")
		cluster1Job.addArguments("-pid=%s" % self.aa_pid)
		cluster1Job.addArguments("-memory=20")

		cluster1Job.uses("350.genecalling.coding.faa", link=Link.INPUT)
		cluster1Job.uses("550.cluster.aa%s.faa" % self.aa_pid, link=Link.OUTPUT, transfer=False)
		cluster1Job.uses("550.cluster.aa%s.mapping" % self.aa_pid, link=Link.OUTPUT, transfer=False)
		
		cluster1Job.profile("globus", "maxwalltime", "10")
		dax.addJob(cluster1Job)
		dax.depends(cluster1Job, geneJob)

		# Blat_prot Job
		blatprotJob = Job("wrapper-blat-prot", node_label="wrapper-blat-prot")
		blatprotJob.addArguments("--input=550.cluster.aa%s.faa" % self.aa_pid)
		blatprotJob.addArguments("--output=650.superblat.sims")

		blatprotJob.uses("550.cluster.aa%s.faa" % self.aa_pid, link=Link.INPUT)
		blatprotJob.uses("650.superblat.sims", link=Link.OUTPUT, transfer=False)
		
		blatprotJob.profile("globus", "maxwalltime", "2880")
                blatprotJob.profile("globus", "hostcount", "24")
                blatprotJob.profile("globus", "count", "24")
		dax.addJob(blatprotJob)
		dax.depends(blatprotJob, cluster1Job)

		# Annotate Sims (Blat Prod) Job
		annotatesims1Job = Job("wrapper-annotate-sims", node_label="wrapper-annotate-sims")
		annotatesims1Job.addArguments("-input=650.superblat.sims")
		annotatesims1Job.addArguments("-out_prefix=650")
		annotatesims1Job.addArguments("-aa")
		annotatesims1Job.addArguments("-ach_ver=%s" % self.ach_annotation_ver)
		annotatesims1Job.addArguments("-ann_file=m5nr_v1.bdb")

		annotatesims1Job.uses("650.superblat.sims", link=Link.INPUT)
		annotatesims1Job.uses("650.aa.sims.filter", link=Link.OUTPUT, transfer=False)
		annotatesims1Job.uses("650.aa.expand.protein", link=Link.OUTPUT, transfer=False)
		annotatesims1Job.uses("650.aa.expand.lca", link=Link.OUTPUT, transfer=False)
		annotatesims1Job.uses("650.aa.expand.ontology", link=Link.OUTPUT, transfer=False)
		
		annotatesims1Job.profile("globus", "maxwalltime", "720")
		dax.addJob(annotatesims1Job)
		dax.depends(annotatesims1Job, blatprotJob)

		# Search RNA Job
		searchJob = Job("wrapper-search-rna", node_label="wrapper-search-rna")
		searchJob.addArguments("-input=100.preprocess.passed.fna")
		searchJob.addArguments("-output=425.search.rna.fna")
		searchJob.addArguments("-rna_nr=%s" % self.m5rna_clust)
		searchJob.addArguments("-size=100")
		searchJob.addArguments("-proc=8")

		searchJob.uses("100.preprocess.passed.fna", link=Link.INPUT)
		searchJob.uses("425.search.rna.fna", link=Link.OUTPUT, transfer=False)

                searchJob.profile("globus", "maxwalltime", "120")
                searchJob.profile("globus", "hostcount", "8")
                searchJob.profile("globus", "count", "8")
                dax.addJob(searchJob)
		dax.depends(searchJob, preprocessJob)

		# CLuster (Search RNA) Job
		cluster2Job = Job("wrapper-cluster", node_label="wrapper-cluster")
                cluster2Job.addArguments("-input=425.search.rna.fna")
                cluster2Job.addArguments("-out_prefix=440.cluster")
                cluster2Job.addArguments("-rna")
                cluster2Job.addArguments("-pid=%s" % self.rna_pid)
                cluster2Job.addArguments("-memory=20")

                cluster2Job.uses("425.search.rna.fna", link=Link.INPUT)
                cluster2Job.uses("440.cluster.rna%s.fna" % self.rna_pid, link=Link.OUTPUT, transfer=False)
                cluster2Job.uses("440.cluster.rna%s.mapping" % self.rna_pid, link=Link.OUTPUT, transfer=False)

                cluster2Job.profile("globus", "maxwalltime", "30")
                dax.addJob(cluster2Job)
		dax.depends(cluster2Job, searchJob)

		# Blat_rna Job
		blatrnaJob = Job("wrapper-blat-rna", node_label="wrapper-blat-rna")
		blatrnaJob.addArguments("--input=440.cluster.rna%s.fna" % self.rna_pid)
		blatrnaJob.addArguments("-rna_nr=m5rna")
		blatrnaJob.addArguments("--output=450.rna.sims")
		blatrnaJob.addArguments("-assembled=%s" % self.assembled)

		blatrnaJob.uses("440.cluster.rna%s.fna" % self.rna_pid, link=Link.INPUT)
		blatrnaJob.uses("450.rna.sims", link=Link.OUTPUT, transfer=False)
		
		blatrnaJob.profile("globus", "maxwalltime", "20")
		dax.addJob(blatrnaJob)
		dax.depends(blatrnaJob, cluster2Job)

		# Annotate Sims (Blat RNA) Job
		annotatesims2Job = Job("wrapper-annotate-sims", node_label="wrapper-annotate-sims")
		annotatesims2Job.addArguments("-input=450.rna.sims")
		annotatesims2Job.addArguments("-out_prefix=450")
		annotatesims2Job.addArguments("-rna")
		annotatesims2Job.addArguments("-ach_ver=%s" % self.ach_annotation_ver)
		annotatesims2Job.addArguments("-ann_file=m5nr_v1.bdb")

		annotatesims2Job.uses("450.rna.sims", link=Link.INPUT)
		annotatesims2Job.uses("450.rna.sims.filter", link=Link.OUTPUT, transfer=False)
		annotatesims2Job.uses("450.rna.expand.rna", link=Link.OUTPUT, transfer=False)
		annotatesims2Job.uses("450.rna.expand.lca", link=Link.OUTPUT, transfer=False)

		annotatesims2Job.profile("globus", "maxwalltime", "30")
		dax.addJob(annotatesims2Job)
		dax.depends(annotatesims2Job, blatrnaJob)

		# Index Sim Seq Job
		indexJob = Job("wrapper-index", node_label="wrapper-index")
		indexJob.addArguments("-in_seqs=350.genecalling.coding.fna")
		indexJob.addArguments("-in_seqs=425.search.rna.fna")
		indexJob.addArguments("-in_maps=550.cluster.aa%s.mapping" % self.aa_pid)
		indexJob.addArguments("-in_maps=440.cluster.rna%s.mapping" % self.rna_pid)
		indexJob.addArguments("-in_sims=650.aa.sims.filter")
		indexJob.addArguments("-in_sims=450.rna.sims.filter")
		indexJob.addArguments("-output=700.annotation.sims.filter.seq")
		indexJob.addArguments("-ach_ver=%s" % self.ach_annotation_ver)
		indexJob.addArguments("-memory=10")
		indexJob.addArguments("-ann_file=m5nr_v1.bdb")

		indexJob.uses("350.genecalling.coding.fna", link=Link.INPUT)
		indexJob.uses("550.cluster.aa%s.mapping" % self.aa_pid, link=Link.INPUT)
		indexJob.uses("650.aa.sims.filter", link=Link.INPUT)
		indexJob.uses("425.search.rna.fna", link=Link.INPUT)
		indexJob.uses("440.cluster.rna%s.mapping" % self.rna_pid, link=Link.INPUT)
		indexJob.uses("450.rna.sims.filter", link=Link.INPUT)
		indexJob.uses("700.annotation.sims.filter.seq", link=Link.OUTPUT, transfer=False)
		indexJob.uses("700.annotation.sims.filter.seq.index", link=Link.OUTPUT, transfer=False)

		indexJob.profile("globus", "maxwalltime", "120")
                dax.addJob(indexJob)
                dax.depends(indexJob, geneJob)
                dax.depends(indexJob, cluster1Job)
                dax.depends(indexJob, cluster2Job)
                dax.depends(indexJob, searchJob)
                dax.depends(indexJob, annotatesims1Job)

		# Annotate Summary Job (13)
		summary13Job = Job("wrapper-summary", node_label="wrapper-summary")
		summary13Job.addArguments("-job=1")
		summary13Job.addArguments("-in_expand=650.aa.expand.protein")
		summary13Job.addArguments("-in_expand=450.rna.expand.rna")
		summary13Job.addArguments("-in_maps=550.cluster.aa%s.mapping" % self.aa_pid)
		summary13Job.addArguments("-in_maps=440.cluster.rna%s.mapping" % self.rna_pid)
		summary13Job.addArguments("-in_assemb=075.assembly.coverage")
		summary13Job.addArguments("-in_index=700.annotation.sims.filter.seq.index")
		summary13Job.addArguments("-output=700.annotation.md5.summary")
		summary13Job.addArguments("-nr_ver=%s" % self.ach_annotation_ver)
		summary13Job.addArguments("-type=md5")

		summary13Job.uses("075.assembly.coverage", link=Link.INPUT)
		summary13Job.uses("550.cluster.aa%s.mapping" % self.aa_pid, link=Link.INPUT)
		summary13Job.uses("650.aa.expand.protein", link=Link.INPUT)
		summary13Job.uses("440.cluster.rna%s.mapping" % self.rna_pid, link=Link.INPUT)
		summary13Job.uses("450.rna.expand.rna", link=Link.INPUT)
		summary13Job.uses("700.annotation.sims.filter.seq.index", link=Link.INPUT)
		summary13Job.uses("700.annotation.md5.summary", link=Link.OUTPUT, transfer=True)

		summary13Job.profile("globus", "maxwalltime", "30")
                dax.addJob(summary13Job)
                dax.depends(summary13Job, qcJob)
                dax.depends(summary13Job, cluster1Job)
                dax.depends(summary13Job, cluster2Job)
                dax.depends(summary13Job, indexJob)
                dax.depends(summary13Job, annotatesims1Job)
                dax.depends(summary13Job, annotatesims2Job)

		# Annotate Summary Job (14)
		summary14Job = Job("wrapper-summary", node_label="wrapper-summary")
		summary14Job.addArguments("-job=1")
		summary14Job.addArguments("-in_expand=650.aa.expand.protein")
		summary14Job.addArguments("-in_expand=450.rna.expand.rna")
		summary14Job.addArguments("-in_maps=550.cluster.aa%s.mapping" % self.aa_pid)
		summary14Job.addArguments("-in_maps=440.cluster.rna%s.mapping" % self.rna_pid)
		summary14Job.addArguments("-in_assemb=075.assembly.coverage")
		summary14Job.addArguments("-output=700.annotation.function.summary")
		summary14Job.addArguments("-nr_ver=%s" % self.ach_annotation_ver)
		summary14Job.addArguments("-type=function")

		summary14Job.uses("075.assembly.coverage", link=Link.INPUT)
		summary14Job.uses("550.cluster.aa%s.mapping" % self.aa_pid, link=Link.INPUT)
		summary14Job.uses("650.aa.expand.protein", link=Link.INPUT)
		summary14Job.uses("440.cluster.rna%s.mapping" % self.rna_pid, link=Link.INPUT)
		summary14Job.uses("450.rna.expand.rna", link=Link.INPUT)
		summary14Job.uses("700.annotation.function.summary", link=Link.OUTPUT, transfer=True)

		summary14Job.profile("globus", "maxwalltime", "30")
                dax.addJob(summary14Job)
                dax.depends(summary14Job, qcJob)
                dax.depends(summary14Job, cluster1Job)
                dax.depends(summary14Job, cluster2Job)
                dax.depends(summary14Job, annotatesims1Job)
                dax.depends(summary14Job, annotatesims2Job)

		# Annotate Summary Job (15)
		summary15Job = Job("wrapper-summary", node_label="wrapper-summary")
		summary15Job.addArguments("-job=1")
		summary15Job.addArguments("-in_expand=650.aa.expand.protein")
		summary15Job.addArguments("-in_expand=450.rna.expand.rna")
		summary15Job.addArguments("-in_maps=550.cluster.aa%s.mapping" % self.aa_pid)
		summary15Job.addArguments("-in_maps=440.cluster.rna%s.mapping" % self.rna_pid)
		summary15Job.addArguments("-in_assemb=075.assembly.coverage")
		summary15Job.addArguments("-output=700.annotation.organism.summary")
		summary15Job.addArguments("-nr_ver=%s" % self.ach_annotation_ver)
		summary15Job.addArguments("-type=organism")

		summary15Job.uses("075.assembly.coverage", link=Link.INPUT)
		summary15Job.uses("550.cluster.aa%s.mapping" % self.aa_pid, link=Link.INPUT)
		summary15Job.uses("650.aa.expand.protein", link=Link.INPUT)
		summary15Job.uses("440.cluster.rna%s.mapping" % self.rna_pid, link=Link.INPUT)
		summary15Job.uses("450.rna.expand.rna", link=Link.INPUT)
		summary15Job.uses("700.annotation.organism.summary", link=Link.OUTPUT, transfer=True)

		summary15Job.profile("globus", "maxwalltime", "30")
                dax.addJob(summary15Job)
                dax.depends(summary15Job, qcJob)
                dax.depends(summary15Job, cluster1Job)
                dax.depends(summary15Job, cluster2Job)
                dax.depends(summary15Job, annotatesims1Job)
                dax.depends(summary15Job, annotatesims2Job)

		# Annotate Summary Job (16)
		summary16Job = Job("wrapper-summary", node_label="wrapper-summary")
		summary16Job.addArguments("-job=1")
		summary16Job.addArguments("-in_expand=650.aa.expand.lca")
		summary16Job.addArguments("-in_expand=450.rna.expand.lca")
		summary16Job.addArguments("-in_maps=550.cluster.aa%s.mapping" % self.aa_pid)
		summary16Job.addArguments("-in_maps=440.cluster.rna%s.mapping" % self.rna_pid)
		summary16Job.addArguments("-in_assemb=075.assembly.coverage")
		summary16Job.addArguments("-output=700.annotation.lca.summary")
		summary16Job.addArguments("-nr_ver=%s" % self.ach_annotation_ver)
		summary16Job.addArguments("-type=lca")

		summary16Job.uses("075.assembly.coverage", link=Link.INPUT)
		summary16Job.uses("550.cluster.aa%s.mapping" % self.aa_pid, link=Link.INPUT)
		summary16Job.uses("650.aa.expand.lca", link=Link.INPUT)
		summary16Job.uses("440.cluster.rna%s.mapping" % self.rna_pid, link=Link.INPUT)
		summary16Job.uses("450.rna.expand.lca", link=Link.INPUT)
		summary16Job.uses("700.annotation.lca.summary", link=Link.OUTPUT, transfer=True)

		summary16Job.profile("globus", "maxwalltime", "30")
                dax.addJob(summary16Job)
                dax.depends(summary16Job, qcJob)
                dax.depends(summary16Job, cluster1Job)
                dax.depends(summary16Job, cluster2Job)
                dax.depends(summary16Job, annotatesims1Job)
                dax.depends(summary16Job, annotatesims2Job)

		# Annotate Summary Job (17)
		summary17Job = Job("wrapper-summary", node_label="wrapper-summary")
		summary17Job.addArguments("-job=1")
		summary17Job.addArguments("-in_expand=650.aa.expand.ontology")
		summary17Job.addArguments("-in_maps=550.cluster.aa%s.mapping" % self.aa_pid)
		summary17Job.addArguments("-in_assemb=075.assembly.coverage")
		summary17Job.addArguments("-output=700.annotation.ontology.summary")
		summary17Job.addArguments("-nr_ver=%s" % self.ach_annotation_ver)
		summary17Job.addArguments("-type=ontology")

		summary17Job.uses("075.assembly.coverage", link=Link.INPUT)
		summary17Job.uses("550.cluster.aa%s.mapping" % self.aa_pid, link=Link.INPUT)
		summary17Job.uses("650.aa.expand.ontology", link=Link.INPUT)
		summary17Job.uses("700.annotation.ontology.summary", link=Link.OUTPUT, transfer=True)

		summary17Job.profile("globus", "maxwalltime", "30")
                dax.addJob(summary17Job)
                dax.depends(summary17Job, qcJob)
                dax.depends(summary17Job, cluster1Job)
                dax.depends(summary17Job, annotatesims1Job)

		# Annotate Summary Job (18)
		summary18Job = Job("wrapper-summary", node_label="wrapper-summary")
		summary18Job.addArguments("-job=1")
		summary18Job.addArguments("-in_expand=650.aa.expand.protein")
		summary18Job.addArguments("-in_expand=450.rna.expand.rna")
		summary18Job.addArguments("-in_maps=550.cluster.aa%s.mapping" % self.aa_pid)
		summary18Job.addArguments("-in_maps=440.cluster.rna%s.mapping" % self.rna_pid)
		summary18Job.addArguments("-in_assemb=075.assembly.coverage")
		summary18Job.addArguments("-output=700.annotation.source.stats")
		summary18Job.addArguments("-nr_ver=%s" % self.ach_annotation_ver)
		summary18Job.addArguments("-type=source")

		summary18Job.uses("075.assembly.coverage", link=Link.INPUT)
		summary18Job.uses("550.cluster.aa%s.mapping" % self.aa_pid, link=Link.INPUT)
		summary18Job.uses("650.aa.expand.protein", link=Link.INPUT)
		summary18Job.uses("440.cluster.rna%s.mapping" % self.rna_pid, link=Link.INPUT)
		summary18Job.uses("450.rna.expand.rna", link=Link.INPUT)
		summary18Job.uses("700.annotation.source.stats", link=Link.OUTPUT, transfer=True)

		summary18Job.profile("globus", "maxwalltime", "30")
                dax.addJob(summary18Job)
                dax.depends(summary18Job, qcJob)
                dax.depends(summary18Job, cluster1Job)
                dax.depends(summary18Job, cluster2Job)
                dax.depends(summary18Job, annotatesims1Job)
                dax.depends(summary18Job, annotatesims2Job)

	
		# Write the DAX file
		dax.writeXMLFile(self.daxfile)

		# Generate the replica catalog
		self.generate_replica_catalog()


def main():
	if len(sys.argv) < 4:
		raise Exception("Usage: %s CONFIGFILE OUTDIR METAGENOMEFILE" % sys.argv[0])

	configfile = sys.argv[1]
	outdir = sys.argv[2]
	mgfile = sys.argv[3]

	if not os.path.isfile(configfile):
		raise Exception("No such file: %s" % configfile)
	if os.path.isdir(outdir):
		raise Exception("Directory exists: %s" % outdir)
        if not os.path.isfile(mgfile):
                raise Exception("No such file: %s" % mgfile)

	# Create the output directory
	outdir = os.path.abspath(outdir)
	os.makedirs(outdir)

	# Read the config file
	config = ConfigParser()
	config.read(configfile)

	 # Generate the workflow in outdir based on the config file
	workflow = MGRASTWorkflow(outdir, config, mgfile)
	workflow.generate_workflow()


if __name__ == '__main__':
	main()
