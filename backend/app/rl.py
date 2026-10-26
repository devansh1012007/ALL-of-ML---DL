"""Reinforcement learning with an honest evaluation (plans C5 and F2).

Why this module exists
----------------------
The old trainer reported whatever reward the algorithm accumulated while it
explored - a number that mixes learning with noise, with no baseline to read
it against. A mean reward measured on the training environment is not a
performance number.

The new contract:

* **Q-Learning (F2)** is the textbook table: a NumPy Q-table with
  epsilon-greedy exploration and decay, for environments whose observation
  and action spaces are both ``Discrete`` (FrozenLake, Taxi, CliffWalking,
  Blackjack by mapping its tuple observation to an integer). Anything else
  is refused with the supported environments named. It needs no torch, so
  it is testable anywhere.
* **Deep RL (C5)** - PPO and DQN - trains as before, but the policy is
  afterwards evaluated on a **fresh environment instance** with fixed seeds
  for N episodes (default 20): the mean and standard deviation of the
  return, the minimum and the maximum, and the success rate where the
  environment defines one. The baseline is the same episodes under a
  uniformly random policy - it is what makes a return interpretable.
* The artifact is a bundle: the Q-table in an ``.npz`` file (plus the
  environment id) or the ``stable-baselines3`` zip (plus the environment id
  and the algorithm), and predict takes a state and returns the action.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from .bundles import BundleError, register_loader
from .charts import cap_charts

# How many fresh episodes the evaluation runs (plan C5).
EVAL_EPISODES = 20
# The reward curve of plan E1 is capped to this many points.
CURVE_POINTS = 200

SUPPORTED_DISCRETE_ENVS = (
    "FrozenLake-v1 (is_slippery=False is the deterministic variant)",
    "Taxi-v3",
    "CliffWalking-v0",
    "Blackjack-v1",
)


def _gymnasium():
    try:
        import gymnasium

        return gymnasium
    except ImportError:
        return None


def _make_env(env_id: str, seed: Optional[int] = None):
    """Create an environment.

    FrozenLake is made non-slippery by default: the deterministic variant
    is the one the Q-learning contract of plan F2 names (a success rate of
    1.0 is reachable within a few thousand steps), and the slippery variant
    makes the *environment* random rather than the policy bad.
    """
    gymnasium = _gymnasium()
    kwargs = {"is_slippery": False} if env_id.startswith("FrozenLake") else {}
    env = gymnasium.make(env_id, **kwargs)
    if seed is not None:
        env.reset(seed=seed)
        # gymnasium's reset(seed=...) seeds only the environment RNG: the
        # action space has its own generator, which reset() leaves at the
        # OS entropy. Seeding it here is what makes "the same seed gives
        # the same run" true (plan F2).
        env.action_space.seed(seed)
    return env


# --- the bundles ------------------------------------------------------------------


class QTableBundle:
    """The artifact of a tabular Q-learning run (plans C1, F2)."""

    kind = "q_table"
    request_kind = "state"

    def __init__(self, q_table: np.ndarray, env_id: str, format_version: int = 1):
        self.q_table = np.asarray(q_table, dtype=float)
        self.env_id = env_id
        self.format_version = format_version

    def schema(self) -> Dict[str, Any]:
        return {
            "request_kind": self.request_kind,
            "kind": self.kind,
            "env_id": self.env_id,
            "n_states": int(self.q_table.shape[0]),
            "n_actions": int(self.q_table.shape[1]),
            "output": "the greedy action for a state, and its Q-values",
        }

    def infer(self, request: Dict[str, Any]) -> Dict[str, Any]:
        state = request.get("state")
        if state is None:
            raise ValueError("The request has no state (an integer state id).")
        try:
            index = int(state)
        except (TypeError, ValueError):
            raise ValueError(f"The state must be an integer, got {state!r}.") from None
        if not 0 <= index < self.q_table.shape[0]:
            raise ValueError(
                f"The state must be between 0 and {self.q_table.shape[0] - 1}, got {index}."
            )
        return {
            "action": int(np.argmax(self.q_table[index])),
            "q_values": [round(float(v), 4) for v in self.q_table[index]],
        }

    def save(self, directory: Path) -> None:
        import json

        np.savez(directory / "q_table.npz", q_table=self.q_table)
        (directory / "config.json").write_text(
            json.dumps(
                {
                    "kind": self.kind,
                    "env_id": self.env_id,
                    "format_version": self.format_version,
                    "n_states": int(self.q_table.shape[0]),
                    "n_actions": int(self.q_table.shape[1]),
                }
            )
        )

    @classmethod
    def load(cls, directory: Path, manifest: Optional[Dict[str, Any]] = None) -> "QTableBundle":
        import json

        config = json.loads((directory / "config.json").read_text())
        with np.load(directory / "q_table.npz") as data:
            q_table = data["q_table"]
        return cls(q_table=q_table, env_id=config["env_id"])


register_loader("q_table", QTableBundle.load)


class RLPolicyBundle:
    """The artifact of a deep-RL run: the SB3 zip plus the environment id
    and the algorithm (plans C1, C5)."""

    kind = "rl_policy"
    request_kind = "state"

    def __init__(self, algorithm: str, env_id: str):
        self.algorithm = algorithm
        self.env_id = env_id
        self.model: Any = None  # the loaded stable-baselines3 model

    def schema(self) -> Dict[str, Any]:
        return {
            "request_kind": self.request_kind,
            "kind": self.kind,
            "algorithm": self.algorithm,
            "env_id": self.env_id,
            "output": "the action the policy takes for an observation",
        }

    def infer(self, request: Dict[str, Any]) -> Dict[str, Any]:
        if self.model is None:
            raise BundleError("The policy is not loaded.")
        observation = request.get("state") or request.get("observation")
        if observation is None:
            raise ValueError("The request has no state (the observation vector).")
        try:
            array = np.asarray(observation, dtype=float)
        except (TypeError, ValueError):
            raise ValueError("The state must be a list of numbers.") from None
        action, _ = self.model.predict(array.reshape(1, -1), deterministic=True)
        return {"action": np.asarray(action).reshape(-1).tolist()}

    def save(self, directory: Path) -> None:
        import json

        if self.model is None:
            raise BundleError("The policy was not trained; there is nothing to save.")
        self.model.save(str(directory / "policy.zip"))
        (directory / "config.json").write_text(
            json.dumps({"algorithm": self.algorithm, "env_id": self.env_id, "kind": self.kind})
        )

    @classmethod
    def load(cls, directory: Path, manifest: Optional[Dict[str, Any]] = None) -> "RLPolicyBundle":
        import json

        config = json.loads((directory / "config.json").read_text())
        bundle = cls(algorithm=config["algorithm"], env_id=config["env_id"])
        try:
            from stable_baselines3 import A2C, DDPG, DQN, PPO, SAC, TD3

            loaders = {"PPO": PPO, "DQN": DQN, "A2C": A2C, "SAC": SAC, "TD3": TD3, "DDPG": DDPG}
            algorithm = config["algorithm"]
            if algorithm not in loaders:
                raise BundleError(f"Unknown RL algorithm '{algorithm}'.")
            bundle.model = loaders[algorithm].load(str(directory / "policy.zip"))
        except ImportError as exc:
            raise BundleError(f"stable-baselines3 is needed to load this policy: {exc}") from None
        return bundle


register_loader("rl_policy", RLPolicyBundle.load)


# --- the evaluation (plan C5) -------------------------------------------------------


def _evaluate_policy(
    policy,
    env_id: str,
    episodes: int = EVAL_EPISODES,
    seed: int = 0,
) -> Dict[str, Any]:
    """Run a policy on a fresh environment with fixed seeds.

    ``policy`` is called with the observation and returns the action, so the
    same evaluation serves the greedy Q-table, the trained SB3 model and the
    uniformly random baseline - which is what makes the numbers comparable.
    """
    gymnasium = _gymnasium()
    if gymnasium is None:
        raise RuntimeError("gymnasium is not installed")
    returns: List[float] = []
    for episode in range(episodes):
        env = _make_env(env_id, seed=seed * 1000 + episode)
        try:
            observation, _ = env.reset(seed=seed * 1000 + episode)
            done = False
            total = 0.0
            while not done:
                action = policy(env, observation)
                observation, reward, terminated, truncated, _ = env.step(action)
                total += float(reward)
                done = terminated or truncated
            returns.append(total)
        finally:
            env.close()
    result: Dict[str, Any] = {
        "episodes": episodes,
        "mean_return": round(float(np.mean(returns)), 4) if returns else None,
        "std_return": round(float(np.std(returns)), 4) if returns else None,
        "min_return": round(float(np.min(returns)), 4) if returns else None,
        "max_return": round(float(np.max(returns)), 4) if returns else None,
    }
    # The success rate where the environment defines one: FrozenLake and
    # Taxi terminate with a reward that says it (a positive return is a
    # success), Blackjack and the control environments do not, and the
    # answer stays None instead of guessing (plan C5).
    positive = [1.0 if value > 0 else 0.0 for value in returns]
    result["success_rate"] = (
        round(float(np.mean(positive)), 4) if any(value > 0 for value in positive) else None
    )
    return result


def _greedy_policy(q_table: np.ndarray):
    def policy(env, observation):
        index = int(observation)
        return int(np.argmax(q_table[index]))

    return policy


def _random_policy(env, observation):
    return env.action_space.sample()


def _sb3_policy(model):
    def policy(env, observation):
        action, _ = model.predict(observation, deterministic=True)
        return np.asarray(action).reshape(-1)[0].item() if np.asarray(action).size == 1 else int(np.asarray(action).reshape(-1)[0])

    return policy


# --- Q-Learning (plan F2) ------------------------------------------------------------


def _observation_index(observation, env) -> int:
    """Map an observation to an integer state id (plan F2).

    A ``Discrete`` observation is already one; Blackjack's tuple observation
    is mapped the way the environment sizes it (the product of the dims).
    """
    import gymnasium as gym

    space = env.observation_space
    if isinstance(space, gym.spaces.Discrete):
        return int(observation)
    if isinstance(space, gym.spaces.Tuple):
        index = 0
        for value, dimension in zip(observation, space):
            index = index * dimension.n + int(value)
        return index
    if isinstance(space, gym.spaces.MultiDiscrete):
        index = 0
        for value, dimension in zip(observation, space.nvec):
            index = index * int(dimension) + int(value)
        return index
    raise ValueError(
        "The observation space must be Discrete (or a tuple of Discrete, like "
        "Blackjack) for tabular Q-learning."
    )


def train_q_learning(env_id: str, params: Dict[str, Any]) -> Tuple[Dict[str, Any], QTableBundle]:
    """The textbook tabular Q-learning (plan F2)."""
    gymnasium = _gymnasium()
    if gymnasium is None:
        raise RuntimeError(
            "gymnasium is not installed: the reinforcement-learning models need it."
        )
    import gymnasium as gym

    try:
        env = _make_env(env_id, seed=int(params.get("random_state", 42)))
    except Exception as exc:
        raise ValueError(f"The environment '{env_id}' could not be created: {exc}") from None
    discrete_obs = isinstance(env.observation_space, gym.spaces.Discrete) or (
        isinstance(env.observation_space, (gym.spaces.Tuple, gym.spaces.MultiDiscrete))
    )
    if not discrete_obs or not isinstance(env.action_space, gym.spaces.Discrete):
        env.close()
        raise ValueError(
            f"Tabular Q-learning needs a discrete state and action space; "
            f"'{env_id}' has observation {env.observation_space} and action "
            f"{env.action_space}. Supported environments: "
            + ", ".join(SUPPORTED_DISCRETE_ENVS)
            + "."
        )

    learning_rate = float(params.get("learning_rate", 0.1))
    discount = float(params.get("discount_factor", 0.99))
    epsilon = float(params.get("epsilon", 1.0))
    epsilon_min = float(params.get("epsilon_min", 0.05))
    epsilon_decay = float(params.get("epsilon_decay", 0.9995))
    training_steps = int(params.get("training_steps", 10000))
    seed = int(params.get("random_state", 42))
    rng = np.random.default_rng(seed)

    n_states = (
        int(env.observation_space.n)
        if isinstance(env.observation_space, gym.spaces.Discrete)
        else int(np.prod([d.n for d in env.observation_space]))
        if isinstance(env.observation_space, gym.spaces.Tuple)
        else int(np.prod(env.observation_space.nvec))
    )
    n_actions = int(env.action_space.n)
    q_table = np.zeros((n_states, n_actions), dtype=float)

    observation, _ = env.reset(seed=seed)
    state = _observation_index(observation, env)
    visited = {state}
    reward_curve: List[float] = []
    episode_return = 0.0
    for step in range(int(training_steps)):
        if rng.random() < epsilon:
            action = int(env.action_space.sample())
        else:
            # The ties of an unvisited state are broken randomly: an argmax
            # over a zero row would pick action 0 forever, and the agent
            # would stand still for the rest of the training (the exploration
            # death spiral the textbook epsilon schedule does not survive).
            best = np.flatnonzero(q_table[state] == q_table[state].max())
            action = int(rng.choice(best))
        observation, reward, terminated, truncated, _ = env.step(action)
        next_state = _observation_index(observation, env)
        visited.add(next_state)
        done = terminated or truncated
        target = float(reward) + (0.0 if done else discount * float(np.max(q_table[next_state])))
        q_table[state, action] += learning_rate * (target - q_table[state, action])
        episode_return += float(reward)
        state = next_state
        if done:
            reward_curve.append(episode_return)
            episode_return = 0.0
            observation, _ = env.reset()
            state = _observation_index(observation, env)
        epsilon = max(epsilon_min, epsilon * epsilon_decay)
    env.close()

    # The honest evaluation (plan C5/F2): the greedy policy on fresh episodes
    # with fixed seeds, next to the uniformly random policy.
    evaluation = _evaluate_policy(_greedy_policy(q_table), env_id, seed=seed)
    baseline = _evaluate_policy(_random_policy, env_id, seed=seed)

    metrics: Dict[str, Any] = {
        "task_type": "reinforcement-learning",
        "algorithm": "Q-Learning",
        "env_id": env_id,
        "training_steps": training_steps,
        "epsilon_final": round(epsilon, 4),
        "states_visited_fraction": round(len(visited) / n_states, 4),
        **{f"baseline_{key}": value for key, value in baseline.items() if key != "episodes"},
        **evaluation,
        "beats_random_baseline": (
            evaluation["mean_return"] is not None
            and baseline["mean_return"] is not None
            and evaluation["mean_return"] > baseline["mean_return"]
        ),
        "artifact_kind": QTableBundle.kind,
    }
    # The reward curve of plan E1, downsampled.
    if reward_curve:
        step = max(1, len(reward_curve) // CURVE_POINTS)
        metrics["_charts"] = cap_charts(
            {"reward_curve": [round(float(v), 3) for v in reward_curve[::step]]}
        )
    return metrics, QTableBundle(q_table=q_table, env_id=env_id)


# --- the deep RL (PPO, DQN) ----------------------------------------------------------


def train_deep_rl(
    model_name: str, env_id: str, params: Dict[str, Any]
) -> Tuple[Dict[str, Any], RLPolicyBundle]:
    """PPO or DQN with the honest evaluation of plan C5."""
    gymnasium = _gymnasium()
    if gymnasium is None:
        raise RuntimeError(
            "gymnasium is not installed: the reinforcement-learning models need it."
        )
    try:
        from stable_baselines3 import DQN, PPO
    except ImportError:
        raise RuntimeError("stable-baselines3 is not installed") from None

    training_steps = int(params.get("training_steps", 10000))
    seed = int(params.get("random_state", 42))
    env = _make_env(env_id)
    try:
        if model_name == "PPO":
            model = PPO(
                "MlpPolicy",
                env,
                learning_rate=float(params.get("learning_rate", 2.5e-4)),
                n_steps=min(int(params.get("n_steps", 2048)), max(64, training_steps)),
                batch_size=int(params.get("batch_size", 64)),
                gamma=float(params.get("gamma", 0.99)),
                ent_coef=float(params.get("ent_coef", 0.01)),
            )
        elif model_name == "DQN":
            model = DQN(
                "MlpPolicy",
                env,
                learning_rate=float(params.get("learning_rate", 1e-4)),
                buffer_size=int(params.get("buffer_size", 100000)),
                learning_starts=min(int(params.get("learning_starts", 1000)), max(100, training_steps // 2)),
                gamma=float(params.get("gamma", 0.99)),
            )
        else:
            raise ValueError(f"Unsupported deep RL model: {model_name}")
        model.learn(total_timesteps=training_steps, progress_bar=False)
    finally:
        env.close()

    # The honest evaluation (plan C5): a fresh environment, fixed seeds, and
    # the random-policy baseline that makes the return readable.
    evaluation = _evaluate_policy(_sb3_policy(model), env_id, seed=seed)
    baseline = _evaluate_policy(_random_policy, env_id, seed=seed)
    metrics: Dict[str, Any] = {
        "task_type": "reinforcement-learning",
        "algorithm": model_name,
        "env_id": env_id,
        "training_steps": training_steps,
        **{f"baseline_{key}": value for key, value in baseline.items() if key != "episodes"},
        **evaluation,
        "beats_random_baseline": (
            evaluation["mean_return"] is not None
            and baseline["mean_return"] is not None
            and evaluation["mean_return"] > baseline["mean_return"]
        ),
        "artifact_kind": RLPolicyBundle.kind,
    }
    bundle = RLPolicyBundle(algorithm=model_name, env_id=env_id)
    bundle.model = model
    return metrics, bundle
