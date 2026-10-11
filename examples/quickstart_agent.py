"""Quickstart: agent distillation — capture teacher trajectories with tools.

Runs fully offline using the built-in `echo` teacher and demo tools.

    python examples/quickstart_agent.py
"""

from __future__ import annotations

from distill.agent import AgentRunner, RunConfig, default_registry
from distill.agent.trajectory import behavior_cloning_examples
from distill.providers import get_provider


def main() -> None:
    teacher = get_provider("echo")
    tools = default_registry()

    runner = AgentRunner(
        teacher,
        tools,
        config=RunConfig(max_steps=5, system_prompt="You are a tool-using agent."),
        reward_fn=lambda t: 1.0 if t.success else 0.0,
        verify_fn=lambda t: bool(t.messages[-1].content.strip()),
    )

    traj = runner.run("Please search for knowledge distillation and summarise it.")
    print(f"steps={traj.num_steps} success={traj.success} reward={traj.reward}")
    for msg in traj.messages:
        print(f"  [{msg.role}] {msg.text()[:90]}")

    examples = behavior_cloning_examples(traj)
    print(f"\nproduced {len(examples)} behaviour-cloning examples")
    if examples:
        print("first example target ->", examples[0]["target"]["content"] or examples[0]["target"].get("tool_calls"))


if __name__ == "__main__":
    main()
