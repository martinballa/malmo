import gym
import ray
from ray.tune import register_env, run_experiments
from pathlib import Path
import malmoenv

ENV_NAME = "malmo"
MISSION_XML = "missions/rllib_multiagent.xml"
COMMAND_PORT = 8999
NUM_MINECRAFT_INSTANCES = 4

xml = Path(MISSION_XML).read_text()

class TrackingEnv(gym.Wrapper):
    def __init__(self, env):
        super().__init__(env)
        self._actions = [
            self._forward,
            self._back,
            self._turn_right,
            self._turn_left,
            self._idle
        ]

    def _reset_state(self):
        self._facing = (1, 0)
        self._position = (0, 0)
        self._visited = {}
        self._update_visited()

    def _forward(self):
        self._position = (
            self._position[0] + self._facing[0],
            self._position[1] + self._facing[1]
        )

    def _back(self):
        self._position = (
            self._position[0] - self._facing[0],
            self._position[1] - self._facing[1]
        )

    def _turn_left(self):
        self._facing = (self._facing[1], -self._facing[0])

    def _turn_right(self):
        self._facing = (-self._facing[1], self._facing[0])

    def _idle(self):
        pass

    def _encode_state(self):
        return self._position

    def _update_visited(self):
        state = self._encode_state()
        value = self._visited.get(state, 0)
        self._visited[state] = value + 1
        return value

    def reset(self):
        self._reset_state()
        return super().reset()

    def step(self, action):
        o, r, d, i = super().step(action)
        self._actions[action]()
        revisit_count = self._update_visited()
        if revisit_count == 0:
            r += 0.02
        if action == 4:
            r += -0.5

        return o, r, d, i


class MalmoSyncEnv(gym.Wrapper):
    def __init__(self, env, idle_action=4):
        super().__init__(env)
        self._idle_action = idle_action

    def reset(self):
        return super().reset()

    def step(self, action):
        o, r, d, i = super().step(action)
        if d:
            return o, r, d, i
        return super().step(self._idle_action)


def create_env(config):
    env = malmoenv.make()
    env.init(xml, COMMAND_PORT + config.worker_index, reshape=True)
    env = MalmoSyncEnv(env)
    env = TrackingEnv(env)
    return env

register_env(ENV_NAME, create_env)

run_experiments({
    "malmo": {
        "run": "IMPALA",
        "env": ENV_NAME,
        "config": {
            "model": {
                "dim": 42
            },
            "num_workers": NUM_MINECRAFT_INSTANCES,
            "rollout_fragment_length": 50,
            "train_batch_size": 1024,
            "replay_buffer_num_slots": 4000,
            "replay_proportion": 10,
            "learner_queue_timeout": 900,
            "num_sgd_iter": 2,
            "num_data_loader_buffers": 2,
        }
    }
})