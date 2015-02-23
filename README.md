# MG-RAST-Workflow

Usage
-----
1. Create/edit configuration file (e.g., mgrast.cfg)

2. Run daxgen.py to generate the workflow in a given directory (e.g., myrun):

    $ python daxgen.py mgrast.cfg myrun

3. Edit plan.sh:
    a. Set the path to the MG-RAST directory (MGRAST_DIR)
    b. Set the path to the MG-RAST pipeline directory (PIPELINE_DIR)
    c. Set the path to your scratch directory (SCRATCH_DIR)
    d. Set the path to your output directory (OUTPUT_DIR)
    e. Set the path to the Pegasus directory (PEGASUS_HOME)
    f. Set the project number (PROJECT)

4. Run plan.sh to plan the workflow:

    $ ./plan.sh myrun

5. Get NERSC grid proxy using:

    $ myproxy-logon -s nerscca.nersc.gov:7512 -t 720 -T -l YOUR_NERSC_USERNAME

6. Follow output of plan.sh to submit workflow

    $ pegasus-run myrun/submit/.../run0001

7. Monitor the workflow:

    $ pegasus-status -l myrun/submit/.../run0001
