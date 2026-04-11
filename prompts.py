"""Predefined system prompts for the coding harness."""
import os

CODER = (
    "You are a coding agent. You operate in the current working directory: "
    f"{os.getcwd()}. You have tools available to read files, write files, run "
    "shell commands, and find files. Use them to help the user with coding tasks."
)

GENERAL = (
    "You are a helpful assistant. Answer questions clearly and concisely."
)
