
one_iter_tool_package = "diengine"
from capture import insert_capture
import os
try:
    import torch_dipu
except:
    pass

from ditk import logging
from ding.model import QAC
from ding.policy import SACPolicy
from ding.envs import BaseEnvManagerV2
from ding.data import DequeBuffer
from ding.config import compile_config
from ding.framework import task, ding_init
from ding.framework.context import OnlineRLContext
from ding.framework.middleware import data_pusher, StepCollector, interaction_evaluator, \
    CkptSaver, OffPolicyLearner, termination_checker, online_logger
from ding.utils import set_pkg_seed
from dizoo.classic_control.pendulum.envs.pendulum_env import PendulumEnv
from dizoo.classic_control.pendulum.config.pendulum_sac_config import main_config, create_config


def main():
    logging.getLogger().setLevel(logging.INFO)
    cfg = compile_config(main_config, create_cfg=create_config, auto=True)

    if( os.getenv('ONE_ITER_TOOL_DEVICE', None) != "cpu"):
        cfg['policy']['cuda']=True
    else:
        cfg['policy']['cuda']=False
    cfg['seed']=5


    ding_init(cfg)
    with task.start(async_mode=False, ctx=OnlineRLContext()):
        collector_env = BaseEnvManagerV2(
            env_fn=[lambda: PendulumEnv(cfg.env) for _ in range(cfg.env.collector_env_num)], cfg=cfg.env.manager
        )
        evaluator_env = BaseEnvManagerV2(
            env_fn=[lambda: PendulumEnv(cfg.env) for _ in range(cfg.env.evaluator_env_num)], cfg=cfg.env.manager
        )

        set_pkg_seed(cfg.seed, use_cuda=cfg.policy.cuda)

        model = QAC(**cfg.policy.model)
        buffer_ = DequeBuffer(size=cfg.policy.other.replay_buffer.replay_buffer_size)
        policy = SACPolicy(cfg.policy, model=model)

        insert_capture(policy, collector_env, evaluator_env, cfg)

        task.use(interaction_evaluator(cfg, policy.eval_mode, evaluator_env))
        task.use(
            StepCollector(cfg, policy.collect_mode, collector_env, random_collect_size=cfg.policy.random_collect_size)
        )
        task.use(data_pusher(cfg, buffer_))
        task.use(OffPolicyLearner(cfg, policy.learn_mode, buffer_))
        task.use(CkptSaver(policy, cfg.exp_name, train_freq=100))
        task.use(termination_checker(max_train_iter=10000))
        task.use(online_logger())
        task.run()


if __name__ == "__main__":
    main()
