#!/usr/bin/env python3
"""Triad Bluff Python starter entrypoint."""

from bluff_agent.adapter import run_agent
from strategy import select_action


if __name__ == "__main__":
    run_agent(select_action)
