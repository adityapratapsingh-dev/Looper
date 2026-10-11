"""Tests for the agent subsystem."""

import unittest

from distill.agent import (
    AgentRunner,
    RunConfig,
    TrajectoryDataset,
    behavior_cloning_examples,
    default_registry,
    filter_trajectories,
)
from distill.agent.tools import ToolRegistry, calculator, knowledge_search
from distill.providers import get_provider
from distill.types import Role, ToolCall, Trajectory


class ToolsTest(unittest.TestCase):
    def test_calculator(self):
        self.assertEqual(calculator("2 * (3 + 4)")["result"], 14)

    def test_calculator_rejects_code(self):
        from distill.errors import ToolExecutionError

        reg = ToolRegistry().add(calculator, name="calculator")
        with self.assertRaises(ToolExecutionError):
            reg.run(ToolCall("calculator", {"expression": "__import__('os').system('echo hi')"}))

    def test_registry_run_to_string_error(self):
        reg = ToolRegistry()
        out = reg.run_to_string(ToolCall("missing", {}))
        self.assertIn("error", out)

    def test_default_registry_has_tools(self):
        reg = default_registry()
        self.assertIn("calculator", reg)
        self.assertIn("word_count", reg)
        self.assertIn("knowledge_search", reg)

    def test_knowledge_search(self):
        self.assertIn("student", knowledge_search("what is distillation")["snippet"].lower())


class RunnerTest(unittest.TestCase):
    def test_runner_produces_trajectory(self):
        runner = AgentRunner(
            get_provider("echo"),
            default_registry(),
            config=RunConfig(max_steps=4, system_prompt="You are helpful."),
        )
        traj = runner.run("please calculate 2 + 2")
        self.assertIsInstance(traj, Trajectory)
        self.assertGreaterEqual(traj.num_steps, 1)
        self.assertEqual(traj.messages[0].role, Role.SYSTEM)
        self.assertEqual(traj.messages[1].role, Role.USER)
        self.assertIn("usage", traj.metadata)

    def test_verifier_and_reward(self):
        runner = AgentRunner(
            get_provider("echo"),
            default_registry(),
            config=RunConfig(max_steps=4),
            reward_fn=lambda t: 1.0 if t.success else 0.0,
            verify_fn=lambda t: "distillation" in t.messages[-1].content.lower(),
        )
        traj = runner.run("search for distillation")
        self.assertTrue(traj.success)
        self.assertEqual(traj.reward, 1.0)

    def test_run_many(self):
        runner = AgentRunner(get_provider("echo"), default_registry(), config=RunConfig(max_steps=3))
        trajs = runner.run_many(["calculate 1+1", "search cats"])
        self.assertEqual(len(trajs), 2)


class TrajectoryDataTest(unittest.TestCase):
    def _traj(self):
        runner = AgentRunner(get_provider("echo"), default_registry(), config=RunConfig(max_steps=4))
        return runner.run("search for agents")

    def test_behavior_cloning(self):
        traj = self._traj()
        examples = behavior_cloning_examples(traj)
        self.assertEqual(len(examples), traj.num_steps)
        self.assertIn("target", examples[0])
        self.assertIn("messages", examples[0])

    def test_dataset_stats_and_filter(self):
        traj = self._traj()
        ds = TrajectoryDataset([traj])
        stats = ds.stats()
        self.assertEqual(stats["num_trajectories"], 1)
        self.assertEqual(len(ds.to_conversations()), 1)
        kept = filter_trajectories([traj], min_reward=10.0)
        self.assertEqual(kept, [])


if __name__ == "__main__":
    unittest.main()
