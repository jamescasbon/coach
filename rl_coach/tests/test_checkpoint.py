#
# Copyright (c) 2019 Intel Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
import os
import shutil
import subprocess
import time
import pytest
import signal
import tempfile
import numpy as np
import pandas as pd
import rl_coach.tests.utils.args_utils as a_utils
from rl_coach import checkpoint
from rl_coach.tests.utils.definitions import Definitions as Def


@pytest.mark.unit_test
def test_get_checkpoint_state():
    files = ['4.test.ckpt.ext', '2.test.ckpt.ext', '3.test.ckpt.ext',
             '1.test.ckpt.ext', 'prefix.10.test.ckpt.ext']
    with tempfile.TemporaryDirectory() as temp_dir:
        [open(os.path.join(temp_dir, fn), 'a').close() for fn in files]
        checkpoint_state = \
            checkpoint.get_checkpoint_state(temp_dir,
                                            all_checkpoints=True)
        assert checkpoint_state.model_checkpoint_path == os.path.join(
            temp_dir, '4.test.ckpt')
        assert checkpoint_state.all_model_checkpoint_paths == \
               [os.path.join(temp_dir, f[:-4]) for f in sorted(files[:-1])]

        reader = \
            checkpoint.CheckpointStateReader(temp_dir,
                                             checkpoint_state_optional=False)
        assert reader.get_latest() is None
        assert len(reader.get_all()) == 0

        reader = checkpoint.CheckpointStateReader(temp_dir)
        assert reader.get_latest().num == 4
        assert [ckp.num for ckp in reader.get_all()] == [1, 2, 3, 4]


@pytest.mark.integration_test
def test_restore_checkpoint(preset_args, clres, start_time=time.time()):
    """ Create checkpoint and restore them in second run."""

    def _create_cmd_and_run(flag):

        run_cmd = [
            'python3', 'rl_coach/coach.py',
            '-p', '{}'.format(preset_args),
            '-e', '{}'.format("ExpName_" + preset_args),
        ]
        test_flag = a_utils.add_one_flag_value(flag=flag)
        run_cmd.extend(test_flag)

        p = subprocess.Popen(run_cmd, stdout=clres.stdout, stderr=clres.stdout)

        return p

    # create logs with
    create_cp_proc = _create_cmd_and_run(flag=['--checkpoint_save_secs', '8'])

    # wait for checkpoint files
    csv_list = a_utils.get_csv_path(clres=clres)
    exp_dir = os.path.dirname(csv_list[0])

    checkpoint_dir = os.path.join(exp_dir, Def.Path.checkpoint)

    checkpoint_test_dir = os.path.join(Def.Path.experiments, 'cp_test_dir')
    if os.path.exists(checkpoint_test_dir):
        shutil.rmtree(checkpoint_test_dir)

    entities = a_utils.get_files_from_dir(checkpoint_dir)

    # wait until we reached 20 steps
    while not any("20_Step" in file for file in entities) and time.time() - \
            start_time < Def.TimeOuts.test_time_limit:
        entities = a_utils.get_files_from_dir(checkpoint_dir)
        time.sleep(1)

    assert "checkpoint" in entities
    assert any(".ckpt." in file for file in entities)

    # send CTRL+C to close experiment
    create_cp_proc.send_signal(signal.SIGINT)

    csv = pd.read_csv(csv_list[0])
    rewards = csv['Evaluation Reward'].values
    rewards = rewards[~np.isnan(rewards)]
    max_reward = np.amax(rewards)

    if os.path.isdir(checkpoint_dir):
        shutil.copytree(exp_dir, checkpoint_test_dir)
        shutil.rmtree(exp_dir)

    create_cp_proc.kill()
    checkpoint_test_dir = "{}/{}".format(checkpoint_test_dir,
                                         Def.Path.checkpoint)
    
    restore_cp_proc = _create_cmd_and_run(flag=['-crd', checkpoint_test_dir,
                                                '--evaluate'])

    new_csv_list = a_utils.get_csv_path(clres=clres)
    time.sleep(Def.TimeOuts.test_run)

    csv = pd.read_csv(new_csv_list[0])
    assert min(csv['Total steps'].values) == max_reward

    restore_cp_proc.kill()
