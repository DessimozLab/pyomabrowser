"""Module that provides a workflow for gc3pie to run
oma fastmapping on a disconnected cluster to which
the omabrowser webserver can ssh to.

Note that this workflow needs to be run in python2 due to
limitations in gc3pie

"""


from gc3libs.cmdline import SessionBasedScript
from gc3libs import Application
from gc3libs.quantity import GB
import os
import shutil
import logging


class FastMappingApp(Application):
    def __init__(self, fasta, out, target=None):
        self.final_out = out
        out_base = os.path.basename(out)
        fasta_base = os.path.basename(fasta)
        cmd = ["fastmap-omamer", fasta_base, out_base]
        if target is not None:
            cmd.append(target)
        Application.__init__(
            self,
            arguments=cmd,
            inputs=[fasta],
            outputs=[out_base],
            output_dir="res_" + out_base,
            stdout="stdout.txt",
            stderr="stderr.txt",
            requested_memory=28 * GB,
        )

    def __del__(self):
        pass

    def terminated(self):
        if self.execution.signal == 0 and self.execution.exitcode == 0:
            if not os.path.basename(self.final_out) in self.outputs:
                logging.error("expected result file not found")
            shutil.move(
                os.path.join(self.output_dir, os.path.basename(self.final_out)),
                self.final_out,
            )
            shutil.rmtree(self.output_dir)


class FastMappingClosestSeqApp(FastMappingApp):
    def __init__(self, fasta, out, target=None):
        self.final_out = out
        out_base = os.path.basename(out)
        fasta_base = os.path.basename(fasta)

        cmd = ["fastmap-closestseq", fasta_base, out_base]
        if target is not None:
            cmd.append(target)

        Application.__init__(
            self,
            arguments=cmd,
            inputs=[fasta],
            outputs=[out_base],
            output_dir="res_" + out_base,
            stdout="stdout.txt",
            stderr="stderr.txt",
            requested_memory=20 * GB,
        )


class FastMappingScript(SessionBasedScript):
    """fast mapping script"""

    version = "1.0"

    def setup_options(self):
        self.add_param("out", help="resulting output file")
        self.add_param("fasta", help="fasta to map")
        self.add_param("method", choices=("s", "st", "h", "ht"),
                       help="mapping method - s: closest sequence, st: clostest seq in target species, "
                            "h: closest hog, ht: closest hog at target level")
        self.add_param("target", help="target species")

    def new_tasks(self, extra):
        if self.params.method in ("h", "ht"):
            tasks = [FastMappingApp(self.params.fasta, self.params.out)]
        elif self.params.method in ('s', 'st'):
            target = self.params.target
            if target is not None and target.lower() == "all":
                target = None
            tasks = [FastMappingClosestSeqApp(
                self.params.fasta, self.params.out, target=target
            )]
        else:
            raise ValueError("Unknown mapping method")
        return tasks


if __name__ == "__main__":
    import fastmapping
    fastmapping.FastMappingScript().run()
