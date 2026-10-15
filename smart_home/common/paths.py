"""Every file location of the smart-home PoC, in one place.

Scripts run as modules from the smart_home folder, e.g.  python -m jev.assistant
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent  # smart_home/
ENV_FILES = (ROOT / ".env", ROOT.parent / ".env")  # API keys; first one found wins per key

# Dataset (dataset/)
DATASET_DIR = ROOT / "dataset"
RAW_DIR = DATASET_DIR / "raw"  # downloaded MASSIVE, git-ignored
MASSIVE_ARCHIVE = RAW_DIR / "amazon-massive-dataset-1.1.tar.gz"
MASSIVE_DIR = RAW_DIR / "massive"
COMMANDS_CSV = DATASET_DIR / "commands.csv"

# Jev (jev/)
JEV_DIR = ROOT / "jev"
SPEC_PATH = JEV_DIR / "spec.json"
SPEC_PROMPT_PATH = JEV_DIR / "spec_prompt.txt"
SPEC_REPLY_PATH = JEV_DIR / "spec_reply.json"
QUESTIONS_PATH = JEV_DIR / "questions.json"
JEV_CONFIG_PATH = JEV_DIR / "config.json"

# LLM baseline (llm/)
LLM_DIR = ROOT / "llm"

# Results: results/<system>/<split>.jsonl, compared by evaluation/evaluate.py
RESULTS_DIR = ROOT / "results"


def system_results(system: str) -> Path:
    """results/<system>/, created on first use."""
    path = RESULTS_DIR / system
    path.mkdir(parents=True, exist_ok=True)
    return path


def load_env() -> None:
    from dotenv import load_dotenv

    for env_file in ENV_FILES:
        load_dotenv(env_file)
