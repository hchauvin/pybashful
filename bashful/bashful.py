# SPDX-License-Identifier: MIT
# Copyright (c) 2020 Hadrien Chauvin

import argparse
import subprocess
import shutil
import os


class Bashful:

    def __init__(self, bashful_serial_mode, force_local_bashful):
        self.bashful_serial_mode = bashful_serial_mode
        self.force_local_bashful = force_local_bashful
        self.bashful_path = None

    def run(self, args, extra_env=None):
        if self.bashful_serial_mode:
            self._bashful_serial(args)
            return

        if not self.bashful_path:
            if self.force_local_bashful:
                self._ensure_local_bashful()
            else:
                self.bashful_path = shutil.which("bashful_path")
                if not self.bashful_path:
                    self._ensure_local_bashful()
        assert self.bashful_path
        subprocess.run(
            [self.bashful_path] + args,
            check=True,
            env={
                **os.environ,
                **(extra_env or {})
            })

    def _ensure_local_bashful(self):
        os.makedirs(os.path.abspath('third-party'), exist_ok=True)
        self.bashful_path = os.path.abspath('third-party/bashful')
        if not os.path.exists(self.bashful_path):
            self._install_bashful()

    def _install_bashful(self):
        subprocess.run([
            'bash', '-c', """
        set -eou pipefail
        
        BASHFUL_VERSION=0.1.1
        
        UNAME=$(uname)
        if [[ "$UNAME" == "Linux" ]]; then
            PLATFORM=linux_amd64
        elif [[ "$UNAME" == "Darwin" ]]; then
            PLATFORM=darwin_amd64
        else
            echo "Platform ${UNAME} is not supported"
            exit 1
        fi
        
        mkdir -p third-party
        cd third-party
        
        URL=https://github.com/wagoodman/bashful/releases/download/v${BASHFUL_VERSION}/bashful_${BASHFUL_VERSION}_${PLATFORM}.tar.gz
        echo "Downloading Bashful from: $URL"
        
        if type wget &> /dev/null; then
            wget $URL
            tar xzfp bashful_${BASHFUL_VERSION}_${PLATFORM}.tar.gz bashful
            rm -f bashful_${BASHFUL_VERSION}_${PLATFORM}.tar.gz
        else
            curl -f -L $URL | tar xzp bashful
        fi
        """
        ],
                       check=True)

    def _bashful_serial(self, args):
        if args[0] != 'run':
            raise Exception("only 'run' is supported in serial mode")
        parser = argparse.ArgumentParser(description='Bashful - serial')
        parser.add_argument('--tags', nargs='*')
        parser.add_argument('pipeline', help='Pipeline file')
        args = parser.parse_args(args[1:])

        tags_to_include = ','.join(
            args.tags or []).split(',') if len(args.tags or []) > 0 else []

        pipeline_path = args.pipeline

        with open(pipeline_path, 'r') as f:
            import yaml
            pipeline = yaml.safe_load(f.read())

        output = "#!/usr/bin/env bash\n\nset -eou pipefail\n\n"

        def output_cmd(name, cmd):
            return f'echo "====== {name} ======"\n' + cmd + "\n"

        for task in pipeline['tasks']:
            task_tags = []
            if task.get('tags'):
                task_tags = task['tags'] if isinstance(
                    task['tags'], list) else [task['tags']]
            skip = True
            if len(task_tags) == 0 or len(tags_to_include) == 0:
                skip = False
            else:
                for task_tag in task_tags:
                    if task_tag in tags_to_include:
                        skip = False
            if skip:
                continue
            task_name = task.get("name", "<anonymous>")
            if task.get("cmd"):
                output += output_cmd(task_name, task['cmd'])
            elif task.get("parallel-tasks"):
                for subtask in task['parallel-tasks']:
                    if subtask.get('cmd'):
                        if subtask.get('for-each'):
                            for item in subtask['for-each']:
                                output += output_cmd(
                                    task_name + " :: " +
                                    (subtask.get("name", "<anonymous>").replace(
                                        '<replace>', item)),
                                    subtask['cmd'].replace('<replace>', item))
                        else:
                            output += output_cmd(
                                task_name + " :: " +
                                subtask.get("name", "<anonymous>"),
                                subtask['cmd'])

        with open(pipeline_path + ".serial.sh", 'w') as f:
            f.write(output)

        subprocess.run(["bash", pipeline_path + ".serial.sh"], check=True)
