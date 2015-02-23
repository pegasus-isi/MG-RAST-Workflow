#!/bin/bash

# User's Configuration
MGRAST_DIR=/global/project/projectdirs/m2187/mgrast
PIPELINE_DIR=$MGRAST_DIR/pipeline
SCRATCH_DIR=/scratch/scratchdirs/rfsilva
OUTPUT_DIR=$MGRAST_DIR/outputs
PEGASUS_HOME=/project/projectdirs/m2187/pegasus/pegasus-4.4.0
PROJECT=m2187

# General Configuration for NERSC sites
SITE=hopper
SITE_URL=hoppergrid.nersc.gov
OUTPUT_SITE=hopper
QUEUE=regular


# Usage
if [ $# -ne 1 ]; then
	echo "Usage: $0 WORKFLOW_DIR"
	exit 1
fi

# Verifying workflow directory
WORKFLOW_DIR=$1
if [ -d "$WORKFLOW_DIR" ]; then
	WORKFLOW_DIR=$(cd $WORKFLOW_DIR && pwd)
else
	echo "No such directory: $WORKFLOW_DIR"
	exit 1
fi

# Parsing Templates
render_template() {
	eval "echo \"$(cat $1)\""
}

mkdir -p ./bin
for template in `ls templates/$SITE`; do
	render_template templates/$SITE/$template > bin/${template%.template}
done


# Workflow Setup
DIR=$(cd $(dirname $0) && pwd)
INPUT_DIR=$DIR/inputs
SUBMIT_DIR=$WORKFLOW_DIR/submit
DAX=$WORKFLOW_DIR/dax.xml
TC=$WORKFLOW_DIR/tc
RC=$WORKFLOW_DIR/rc
SC=$WORKFLOW_DIR/sites.xml
PP=$DIR/pegasus.properties

render_template $RC.template > $RC
render_template $DIR/sites.template > $SC

# Generating Transformation Catalog
echo "# MG-RAST Transformation Catalog" > $TC

for exec in `ls ./bin`; do
cat << EOF >> $TC

tr ${exec%.sh} {
        site local {
                pfn "$DIR/bin/$exec"
                arch "x86_64"
                os "linux"
                type "STAGEABLE"
        }
}
EOF
done


echo "Planning workflow..."
pegasus-plan \
	-Dpegasus.catalog.site.file=$SC \
	-Dpegasus.catalog.replica=File \
	-Dpegasus.catalog.replica.file=$RC \
	-Dpegasus.catalog.transformation.file=$TC \
	--conf $PP \
	--dax $DAX \
	--dir $SUBMIT_DIR \
	--input-dir $INPUT_DIR \
	--sites $SITE \
	--output-site $OUTPUT_SITE \
	--cleanup leaf \
	--force
