#!/usr/bin/env python3
"""Triad Bluff tournament agent entrypoint (stdlib only)."""

from bluff_agent.adapter import run_agent
from strategy import select_action


if __name__ == "__main__":
    run_agent(select_action)
