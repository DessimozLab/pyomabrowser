"""Module that provides a workflow for gc3pie to run
oma standalone export on a disconnected cluster to which
the omabrowser webserver can ssh to.

Note that this workflow needs to be run in python2 due to
limitations in gc3pie

"""


from gc3libs.cmdline import SessionBasedScript
from gc3libs import Application
from gc3libs.quantity import GB
import tempfile
import os
import shutil
import logging


class StandaloneExportApp(Application):
    def __init__(self, genomes, out):
        self.final_out = out
        out_base = os.path.basename(out)
        quoted_genomes = map(lambda g: "'{}'".format(g), genomes)
        with tempfile.NamedTemporaryFile(prefix="standalone_cmd", delete=False) as fh:
            fh.write("genomes := [{}]:\nfn := '{}':\n"
                     .format(", ".join(quoted_genomes), out_base))
            fh.write("printlevel := 2;\n");
            fh.write("ReadProgram(getenv('HOME').'/Browser/AllAllExport_bgscript.drw');\n")
            fh.write("done;\n");
        self.cmdfile = fh.name
        Application.__init__(
           self,
           arguments=["darwin", "-i", os.path.basename(self.cmdfile)],
           inputs=[self.cmdfile],
           outputs=[out_base],
           output_dir="res_"+out_base,
           stdout="stdout.txt",
           stderr="stderr.txt",
           requested_memory=20*GB)

    def __del__(self):
        os.remove(self.cmdfile)

    def terminated(self):
        if self.execution.signal == 0 and self.execution.exitcode == 0:
            if not os.path.basename(self.final_out) in self.outputs:
                logging.error('expected result file not found')
            shutil.move(os.path.join(self.output_dir, os.path.basename(self.final_out)),
                        self.final_out)
            shutil.rmtree(self.output_dir)


class StandaloneExportScript(SessionBasedScript):
    """Export OMA standalone script"""
    version = "1.0"

    def setup_options(self):
        self.add_param('out', help="resulting output file")
        self.add_param('genome', nargs='+', help='genomes to export')

    def new_tasks(self, extra):
        tasks = [StandaloneExportApp(self.params.genome, self.params.out)]
        return tasks


if __name__ == "__main__":
    import gc3workflow
    gc3workflow.StandaloneExportScript().run()