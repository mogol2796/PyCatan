# Catan Simulation in Python

A Settlers of Catan simulator for AI agents written in Python.

## Overview

This repository contains a Python-based simulator for the board game Settlers of Catan. It is designed to test and refine AI agents in a simulated environment. Users can execute predefined agents, as well as introduce their own custom agents into the game.

## Getting Started

### Prerequisites

Ensure you have Python installed on your machine. The simulation is compatible with Python 3.x.

### Adding Your Agents

1. Navigate to the `Agents` folder.
2. Place your custom agent module or Python file in this folder.
3. Ensure your agent class is correctly defined within the module.

### Running the Simulator

To run the simulator, use the `main` module. Specify the agents to be executed and the number of games to be played. Each agent should be referenced by the module or file name, followed by a dot, and then the class name (e.g., `MyModule.MyClass`).

### Results

After each game, the result is displayed in the console and the game trace is saved in JSON format in the `Traces` folder.

## LLM Agents (Experimental)

This project can run agents that query an external LLM to decide moves. A reference implementation is included as `Agents/LLMJsonAgent.py`.

### Providers

Select the backend with `LLM_PROVIDER`:

- *(default)* `openai` / `openai_compat`: OpenAI-compatible Chat Completions (also works with UPV gateways and Ollama OpenAI-compat)
- `ollama`: native Ollama `http://localhost:11434/api/chat`
- `bedrock`: AWS Bedrock Runtime (Converse API)

### Configuration

Common env vars:

- `LLM_MODEL` (model name / id)
- Optional: `LLM_TIMEOUT_S`, `LLM_TEMPERATURE`, `LLM_MAX_TOKENS`
- Optional: `LLM_LOG_DIR` (writes one `.jsonl` log file per process)
- Optional: `LLM_BUILD_ACTIONS` (build actions per turn, default `3`)
- Optional: `LLM_START_CANDIDATES` (initial placement candidates, default `12`)

OpenAI-compatible (`LLM_PROVIDER=openai_compat`):

- `LLM_API_BASE` (e.g. `https://api.openai.com/v1`, or your UPV gateway base ending in `/v1`)
- Optional/required depending on provider: `LLM_API_KEY`

Ollama native (`LLM_PROVIDER=ollama`):

- `OLLAMA_BASE_URL` (defaults to `http://localhost:11434`)
- `OLLAMA_MODEL` (or `LLM_MODEL`)

AWS Bedrock (`LLM_PROVIDER=bedrock`):

- `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, optional `AWS_SESSION_TOKEN`
- `AWS_REGION` (or `BEDROCK_REGION`)
- `BEDROCK_MODEL_ID` (or `LLM_MODEL`)

### Run with the LLM agent

1. Run `python main.py`
2. When asked for the agent module/class, use `LLMJsonAgent.LLMJsonAgent` for the seat(s) you want.

Note: LLM-based games will be slower and may hit rate limits/cost, especially if you run large benchmarks with multiprocessing.

## Visualizing Results

To visualize game results:
1. Open the `index.html` file located in the `Visualizer` folder.
2. Load a JSON trace file by clicking on the three-dot icon located in the controls below the right side of the Catan board.

<img src="assets/visualizer_screenshot.png" width="900" alt="Screenshot of the visualizer">


## Contributing

Contributions to the Catan Simulation in Python are welcome! Please feel free to make changes and submit pull requests.
